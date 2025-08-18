from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import psycopg2.extras
from datetime import datetime
import pandas as pd
import os
from functools import wraps
import pytz
import io
from urllib.parse import urlparse

# 新增：匯入圖片處理模組
from image_utils import process_and_upload_image, delete_equipment_images

app = Flask(__name__)

# 生產環境配置
if os.environ.get('RENDER'):
    app.secret_key = os.environ.get('SECRET_KEY', 'fallback-secret-key-change-me')
    DATABASE_URL = os.environ.get('DATABASE_URL')
else:
    app.secret_key = 'your-secret-key-here'
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost/guitar_club')

# 設定台灣時區
TW_TZ = pytz.timezone('Asia/Taipei')

def get_taiwan_time():
    """取得台灣當前時間"""
    return datetime.now(TW_TZ).strftime('%Y-%m-%d %H:%M:%S')

def get_db_connection():
    """取得資料庫連接"""
    # 只保留 PostgreSQL 連接
    db_url = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    conn = psycopg2.connect(db_url)
    conn.autocommit = False  # 手動控制事務
    return conn

# 資料庫初始化和遷移
def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # PostgreSQL 版本的建表語句
        # 創建用戶表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                student_id VARCHAR(50) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL,
                class_name VARCHAR(100) NOT NULL,
                club_role VARCHAR(50) NOT NULL,
                password VARCHAR(255) NOT NULL,
                is_admin INTEGER DEFAULT 0,
                created_at TIMESTAMP NOT NULL
            )
        ''')
        
        # 創建器材表 - 包含圖片欄位和軟刪除欄位
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS equipment (
                id SERIAL PRIMARY KEY,
                category VARCHAR(100) NOT NULL,
                model VARCHAR(200) NOT NULL,
                total_quantity INTEGER NOT NULL DEFAULT 1,
                available_quantity INTEGER NOT NULL DEFAULT 1,
                image_full_url TEXT,
                image_thumb_url TEXT,
                deleted_at TIMESTAMP NULL
            )
        ''')
        
        # 創建租借記錄表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rental_records (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                equipment_id INTEGER NOT NULL,
                rental_time TIMESTAMP NOT NULL,
                return_time TIMESTAMP NULL,
                expected_return_date DATE NULL,
                rental_days INTEGER NULL,
                status VARCHAR(20) DEFAULT 'borrowed',
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (equipment_id) REFERENCES equipment (id)
            )
        ''')
        
        # 檢查並添加圖片欄位（遷移邏輯）
        try:
            cursor.execute('''
                ALTER TABLE equipment 
                ADD COLUMN IF NOT EXISTS image_full_url TEXT
            ''')
        except Exception as e:
            print(f"Column image_full_url might already exist: {e}")
        
        try:
            cursor.execute('''
                ALTER TABLE equipment 
                ADD COLUMN IF NOT EXISTS image_thumb_url TEXT
            ''')
        except Exception as e:
            print(f"Column image_thumb_url might already exist: {e}")
        
        # 新增：軟刪除欄位
        try:
            cursor.execute('''
                ALTER TABLE equipment 
                ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP NULL
            ''')
        except Exception as e:
            print(f"Column deleted_at might already exist: {e}")
            
        # 檢查並添加新欄位（遷移邏輯）
        try:
            cursor.execute('''
                ALTER TABLE rental_records 
                ADD COLUMN IF NOT EXISTS expected_return_date DATE
            ''')
        except Exception as e:
            print(f"Column expected_return_date might already exist: {e}")
        
        try:
            cursor.execute('''
                ALTER TABLE rental_records 
                ADD COLUMN IF NOT EXISTS rental_days INTEGER
            ''')
        except Exception as e:
            print(f"Column rental_days might already exist: {e}")
        
        # 插入預設器材（包含數量）
        equipment_data = [
            ('插電吉他', 'Fender Stratocaster', 2),
            ('插電吉他', 'Ibanez RG', 3),
            ('插電吉他', 'Gibson Les Paul', 1),
            ('不插電吉他', 'Yamaha FG830', 4),
            ('不插電吉他', 'Martin D-28', 1),
            ('不插電吉他', 'Taylor 814ce', 2),
            ('控台', 'Behringer X32', 1),
            ('控台', 'Yamaha MG16XU', 2),
            ('喇叭', 'JBL EON615', 3),
            ('喇叭', 'Yamaha DBR15', 2),
        ]
        
        cursor.execute('SELECT COUNT(*) FROM equipment WHERE deleted_at IS NULL')
        if cursor.fetchone()[0] == 0:
            cursor.executemany(
                'INSERT INTO equipment (category, model, total_quantity, available_quantity) VALUES (%s, %s, %s, %s)', 
                [(item[0], item[1], item[2], item[2]) for item in equipment_data]
            )
        
        # 創建預設管理員帳號
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
        if cursor.fetchone()[0] == 0:
            admin_password = generate_password_hash('qwert')
            admin_created_time = get_taiwan_time()
            cursor.execute('''
                INSERT INTO users (student_id, name, class_name, club_role, password, is_admin, created_at) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', ('fcuguitar', '系統管理員', '管理組', '系統管理員', admin_password, 1, admin_created_time))
        
        conn.commit()
        conn.close()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Database initialization error: {e}")

# 全域變數確保只初始化一次
_db_initialized = False

def ensure_db_initialized():
    """確保資料庫已初始化"""
    global _db_initialized
    if not _db_initialized:
        init_db()
        _db_initialized = True

def execute_query(query, params=None, fetch=None):
    """統一的查詢執行函數"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(query, params)
        
        result = None
        if fetch == 'one':
            result = cursor.fetchone()
        elif fetch == 'all':
            result = cursor.fetchall()
        
        conn.commit()
        return result
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# 登入檢查裝飾器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ensure_db_initialized()
        if 'user_id' not in session:
            # 保存當前頁面 URL，登入後可以回到原頁面
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# 管理員檢查裝飾器
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ensure_db_initialized()
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        user = execute_query('SELECT is_admin FROM users WHERE id = %s', (session['user_id'],), fetch='one')
        
        if not user or not user[0]:
            flash('需要管理員權限', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    ensure_db_initialized()
    # 如果已經登入，直接跳轉到對應頁面
    if 'user_id' in session:
        if session.get('is_admin'):
            return redirect(url_for('admin_panel'))
        else:
            return redirect(url_for('dashboard'))
    # 未登入則顯示登入頁面
    return redirect(url_for('login'))

@app.route('/health')
def health_check():
    ensure_db_initialized()
    return {
        'status': 'healthy', 
        'timestamp': get_taiwan_time(),
        'message': 'Guitar Club System is running',
        'database': 'PostgreSQL'
    }

@app.route('/register', methods=['GET', 'POST'])
def register():
    ensure_db_initialized()
    if request.method == 'POST':
        student_id = request.form['student_id']
        name = request.form['name']
        class_name = request.form['class_name']
        club_role = request.form['club_role']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('密碼確認不符', 'error')
            return render_template('register.html')
        
        hashed_password = generate_password_hash(password)
        created_time = get_taiwan_time()
        
        try:
            execute_query('''
                INSERT INTO users (student_id, name, class_name, club_role, password, created_at) 
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (student_id, name, class_name, club_role, hashed_password, created_time))
            
            flash('註冊成功！請登入', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            if 'unique' in str(e).lower() or 'duplicate' in str(e).lower():
                flash('此學號已被註冊', 'error')
            else:
                flash('註冊失敗，請稍後再試', 'error')
            return render_template('register.html')
    
    return render_template('register.html')

from datetime import timedelta

# 設定 session 過期時間
app.permanent_session_lifetime = timedelta(days=30)

@app.route('/login', methods=['GET', 'POST'])
def login():
    ensure_db_initialized()
    
    # 如果已經登入，重定向到對應頁面
    if 'user_id' in session:
        if session.get('is_admin'):
            return redirect(url_for('admin_panel'))
        else:
            return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        student_id = request.form['student_id']
        password = request.form['password']
        remember_me = request.form.get('remember_me')  # 記住我選項
        
        user = execute_query('SELECT id, name, password, is_admin FROM users WHERE student_id = %s', (student_id,), fetch='one')
        
        if user and check_password_hash(user[2], password):
            # 設定 session
            session['user_id'] = user[0]
            session['user_name'] = user[1]
            session['is_admin'] = user[3]
            
            # 如果勾選記住我，設定為永久 session
            if remember_me:
                session.permanent = True
            
            flash(f'歡迎回來，{user[1]}！', 'success')
            
            # 檢查是否有重定向參數（例如從需要登入的頁面跳轉過來）
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            
            # 根據用戶角色決定跳轉頁面
            if user[3]:  # is_admin == 1
                return redirect(url_for('admin_panel'))
            else:
                return redirect(url_for('dashboard'))
        else:
            flash('學號或密碼錯誤', 'error')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    user_name = session.get('user_name', '用戶')
    session.clear()
    flash(f'{user_name} 已安全登出', 'info')
    return redirect(url_for('login')) 

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 取得器材類別（排除已刪除的）
    cursor.execute('SELECT DISTINCT category FROM equipment WHERE deleted_at IS NULL')
    categories = [row[0] for row in cursor.fetchall()]
    
    # 取得用戶的租借記錄（按時間和器材分組）- 不過濾已刪除器材，保留歷史記錄
    cursor.execute('''
        SELECT rr.rental_time, e.category, e.model, 
               COUNT(*) as quantity,
               MAX(rr.id) as latest_id,
               SUM(CASE WHEN rr.status = 'borrowed' THEN 1 ELSE 0 END) as borrowed_count,
               MIN(rr.return_time) as first_return_time,
               MAX(rr.return_time) as last_return_time
        FROM rental_records rr
        JOIN equipment e ON rr.equipment_id = e.id
        WHERE rr.user_id = %s
        GROUP BY rr.rental_time, e.id
        ORDER BY rr.rental_time DESC
        LIMIT 10
    ''', (session['user_id'],))
    
    user_rentals = cursor.fetchall()
    conn.close()
    
    return render_template('dashboard.html', categories=categories, user_rentals=user_rentals)

@app.route('/get_models/<category>')
@login_required
def get_models(category):
    # 修改查詢以包含圖片 URL，排除已刪除的器材
    models = execute_query('''
        SELECT id, model, available_quantity, total_quantity, image_thumb_url
        FROM equipment 
        WHERE category = %s AND available_quantity > 0 AND deleted_at IS NULL
    ''', (category,), fetch='all')
    
    return {'models': [
        {
            'id': model[0], 
            'name': f"{model[1]} (可借: {model[2]}/{model[3]})",
            'available': model[2],
            'thumb_url': model[4]  # 新增縮圖 URL
        } for model in models
    ]}

@app.route('/borrow_equipment', methods=['POST'])
@login_required
def borrow_equipment():
    equipment_id = request.form['equipment_id']
    borrow_quantity = int(request.form.get('borrow_quantity', 1))
    rental_duration = request.form.get('rental_duration')
    time_unit = request.form.get('time_unit', 'days')
    
    # 處理租借時間（必填）
    if not rental_duration or not rental_duration.strip():
        flash('請輸入預計租借時間', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        duration_value = float(rental_duration)
        if duration_value <= 0:
            flash('租借時間必須是正數', 'error')
            return redirect(url_for('dashboard'))
    except ValueError:
        flash('租借時間必須是有效的數字', 'error')
        return redirect(url_for('dashboard'))
    
    from datetime import timedelta
    import pytz

    # 使用台灣時區進行計算
    current_datetime = datetime.now(TW_TZ)

    if time_unit == 'hours':
        expected_return_datetime = current_datetime + timedelta(hours=duration_value)
        rental_days_decimal = duration_value / 24
        rental_days_int = max(1, round(duration_value / 24))  # 至少1天，四捨五入
        time_display = f"{duration_value} 小時"
        if duration_value >= 24:
            time_display += f" (約 {rental_days_int} 天)"
    else:  # days
        expected_return_datetime = current_datetime + timedelta(days=duration_value)
        rental_days_decimal = duration_value
        rental_days_int = int(duration_value)
        time_display = f"{int(duration_value)} 天"

    # 格式化為字串，保持台灣時區
    expected_return_date = expected_return_datetime.strftime('%Y-%m-%d %H:%M')

    print(f"Debug - Current time: {current_datetime}")
    print(f"Debug - Expected return: {expected_return_datetime}")
    print(f"Debug - Duration: {duration_value} {time_unit}")
    print(f"Debug - Rental days decimal: {rental_days_decimal}")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 檢查器材是否可用
        cursor.execute('''
            SELECT model, available_quantity 
            FROM equipment 
            WHERE id = %s AND available_quantity >= %s AND deleted_at IS NULL
        ''', (equipment_id, borrow_quantity))
        
        equipment = cursor.fetchone()
        
        if not equipment:
            flash('器材庫存不足或不存在', 'error')
            conn.close()
            return redirect(url_for('dashboard'))
        
        # 批量記錄租借（每件器材一筆記錄）
        current_time = get_taiwan_time()
        for i in range(borrow_quantity):
            cursor.execute('''
                INSERT INTO rental_records (user_id, equipment_id, rental_time, expected_return_date, rental_days) 
                VALUES (%s, %s, %s, %s, %s)
            ''', (session['user_id'], equipment_id, current_time, expected_return_date, rental_days_decimal))
        
        # 減少可用數量
        cursor.execute('''
            UPDATE equipment 
            SET available_quantity = available_quantity - %s 
            WHERE id = %s
        ''', (borrow_quantity, equipment_id))
        
        conn.commit()
        
        quantity_text = f'{borrow_quantity} 件' if borrow_quantity > 1 else '1 件'
        flash(f'成功借用 {equipment[0]} {quantity_text}，預計租借 {time_display}', 'success')
    except Exception as e:
        conn.rollback()
        flash('借用失敗，請稍後再試', 'error')
        print(f"Borrow error: {e}")
    finally:
        conn.close()
    
    return redirect(url_for('dashboard'))

@app.route('/return_equipment_batch', methods=['GET', 'POST'])
@login_required
def return_equipment_batch():
    if request.method == 'GET':
        rental_time = request.args.get('rental_time')
        equipment_category = request.args.get('category')
        equipment_model = request.args.get('model')
        return_quantity = None
        use_rental_time = True
    else:
        equipment_category = request.form['category']
        equipment_model = request.form['model']
        return_quantity = int(request.form['return_quantity'])
        rental_time = request.form.get('rental_time')
        use_rental_time = bool(rental_time)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if use_rental_time:
            cursor.execute('''
                SELECT rr.id 
                FROM rental_records rr
                JOIN equipment e ON rr.equipment_id = e.id
                WHERE rr.user_id = %s AND rr.rental_time = %s 
                      AND e.category = %s AND e.model = %s AND rr.status = 'borrowed'
                ORDER BY rr.id
            ''', (session['user_id'], rental_time, equipment_category, equipment_model))
        else:
            cursor.execute('''
                SELECT rr.id 
                FROM rental_records rr
                JOIN equipment e ON rr.equipment_id = e.id
                WHERE rr.user_id = %s AND e.category = %s AND e.model = %s AND rr.status = 'borrowed'
                ORDER BY rr.rental_time ASC, rr.id ASC
            ''', (session['user_id'], equipment_category, equipment_model))
        
        records = cursor.fetchall()
        if not records:
            flash('找不到可歸還的記錄', 'error')
            conn.close()
            return redirect(url_for('dashboard'))
        
        actual_return_quantity = return_quantity if return_quantity else len(records)
        if actual_return_quantity > len(records):
            flash('歸還數量超過可歸還數量', 'error')
            conn.close()
            return redirect(url_for('dashboard'))
        
        records_to_return = records[:actual_return_quantity]
        return_time = get_taiwan_time()
        
        # 更新歸還時間和狀態
        for record in records_to_return:
            cursor.execute('''
                UPDATE rental_records 
                SET return_time = %s, status = 'returned' 
                WHERE id = %s
            ''', (return_time, record[0]))
        
        # 更新器材可用數量
        equipment_ids_to_update = set()
        for record in records_to_return:
            # 找出這個記錄對應的器材ID
            cursor.execute('SELECT equipment_id FROM rental_records WHERE id = %s', (record[0],))
            equipment_id = cursor.fetchone()[0]
            equipment_ids_to_update.add(equipment_id)
        
        # 為每個器材增加歸還的數量
        for equipment_id in equipment_ids_to_update:
            # 計算這個器材在這批歸還中的數量
            equipment_return_count = 0
            for record in records_to_return:
                cursor.execute('SELECT equipment_id FROM rental_records WHERE id = %s', (record[0],))
                if cursor.fetchone()[0] == equipment_id:
                    equipment_return_count += 1
            
            cursor.execute('''
                UPDATE equipment 
                SET available_quantity = available_quantity + %s 
                WHERE id = %s
            ''', (equipment_return_count, equipment_id))
        
        conn.commit()
        flash(f'成功歸還 {actual_return_quantity} 件 {equipment_category} - {equipment_model}', 'success')
    except Exception as e:
        conn.rollback()
        flash('歸還失敗，請稍後再試', 'error')
        print(f"Return error: {e}")
    finally:
        conn.close()
    
    return redirect(url_for('dashboard'))

@app.route('/admin')
@admin_required
def admin_panel():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 取得所有會員資訊
        cursor.execute('SELECT id, student_id, name, class_name, club_role, created_at FROM users WHERE is_admin = 0')
        members = cursor.fetchall()
        
        # 取得所有租借記錄 - 保留已刪除器材的歷史記錄
        cursor.execute('''
            WITH rental_base AS (
                SELECT u.name, u.student_id, e.category, e.model, 
                       rr.rental_time, rr.return_time, rr.status,
                       rr.user_id, rr.equipment_id
                FROM rental_records rr
                JOIN users u ON rr.user_id = u.id
                JOIN equipment e ON rr.equipment_id = e.id
            ),
            rental_counts AS (
                SELECT user_id, equipment_id, rental_time,
                       COUNT(*) as total_count,
                       SUM(CASE WHEN status = 'borrowed' THEN 1 ELSE 0 END) as borrowed_count
                FROM rental_records rr
                JOIN equipment e ON rr.equipment_id = e.id
                GROUP BY user_id, equipment_id, rental_time
            ),
            rental_summary AS (
                -- 原始租借記錄
                SELECT rb.name, rb.student_id, rb.category, rb.model, 
                       rb.rental_time, 
                       NULL as return_time,
                       rc.total_count as batch_quantity,
                       'rental' as record_type,
                       rc.total_count as total_rental_quantity,
                       rc.borrowed_count as remaining_borrowed,
                       0 as sort_order
                FROM rental_base rb
                JOIN rental_counts rc ON rb.user_id = rc.user_id 
                    AND rb.equipment_id = rc.equipment_id 
                    AND rb.rental_time = rc.rental_time
                GROUP BY rb.name, rb.student_id, rb.category, rb.model, rb.rental_time,
                         rc.total_count, rc.borrowed_count
                
                UNION ALL
                
                -- 歸還記錄
                SELECT rb.name, rb.student_id, rb.category, rb.model, 
                       rb.rental_time, rb.return_time,
                       COUNT(*) as batch_quantity,
                       'return' as record_type,
                       rc.total_count as total_rental_quantity,
                       rc.borrowed_count as remaining_borrowed,
                       1 as sort_order
                FROM rental_base rb
                JOIN rental_counts rc ON rb.user_id = rc.user_id 
                    AND rb.equipment_id = rc.equipment_id 
                    AND rb.rental_time = rc.rental_time
                WHERE rb.return_time IS NOT NULL
                GROUP BY rb.name, rb.student_id, rb.category, rb.model, 
                         rb.rental_time, rb.return_time, rc.total_count, rc.borrowed_count
            )
            SELECT name, student_id, category, model, rental_time, return_time,
                   batch_quantity, record_type, total_rental_quantity, remaining_borrowed
            FROM rental_summary
            ORDER BY rental_time DESC, sort_order ASC, 
                     CASE WHEN return_time IS NULL THEN '9999-12-31 23:59:59'::timestamp ELSE return_time END DESC
            LIMIT 100
        ''')
        all_rentals = cursor.fetchall()
        
        # 取得未歸還的器材（加入租借天數和預計歸還日期）- 排除已刪除器材
        cursor.execute('''
            SELECT u.name, u.student_id, e.category, e.model, 
                   COUNT(*) as total_borrowed_count,
                   MIN(rr.rental_time) as first_rental_time,
                   MAX(rr.rental_time) as last_rental_time,
                   MAX(rr.rental_days) as rental_days,
                   MAX(rr.expected_return_date) as expected_return_date
            FROM rental_records rr
            JOIN users u ON rr.user_id = u.id
            JOIN equipment e ON rr.equipment_id = e.id
            WHERE rr.status = 'borrowed' AND e.deleted_at IS NULL
            GROUP BY u.id, e.id, u.name, u.student_id, e.category, e.model
            ORDER BY first_rental_time ASC
        ''')
        unreturned = cursor.fetchall()
        
        # 取得器材庫存狀況（包含圖片 URL，排除已刪除的）
        cursor.execute('''
            SELECT e.id, e.category, e.model, e.total_quantity, e.available_quantity,
                   (e.total_quantity - e.available_quantity) as borrowed_quantity,
                   e.image_full_url, e.image_thumb_url
            FROM equipment e
            WHERE e.deleted_at IS NULL
            ORDER BY e.category, e.model
        ''')
        equipment_status = cursor.fetchall()
        
        conn.close()
        return render_template('admin.html', 
                             members=members, 
                             all_rentals=all_rentals, 
                             unreturned=unreturned,
                             equipment_status=equipment_status)
    except Exception as e:
        conn.close()
        flash('載入管理介面失敗，請稍後再試', 'error')
        print(f"Admin panel error: {e}")
        return redirect(url_for('dashboard'))

@app.route('/update_equipment', methods=['POST'])
@admin_required
def update_equipment():
    equipment_id = request.form['equipment_id']
    new_total_quantity = int(request.form['total_quantity'])
    
    # 處理圖片上傳（如果有的話）
    image_file = request.files.get('equipment_image')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 取得目前器材資訊（確保器材未被刪除）
        cursor.execute('''
            SELECT total_quantity, available_quantity, model 
            FROM equipment WHERE id = %s AND deleted_at IS NULL
        ''', (equipment_id,))
        equipment = cursor.fetchone()
        
        if not equipment:
            flash('器材不存在', 'error')
            conn.close()
            return redirect(url_for('admin_panel'))
        
        current_total, current_available, model_name = equipment
        borrowed_quantity = current_total - current_available
        
        # 檢查新總數是否小於已借出數量
        if new_total_quantity < borrowed_quantity:
            flash(f'錯誤：{model_name} 目前已借出 {borrowed_quantity} 件，總數量不能少於已借出數量', 'error')
            conn.close()
            return redirect(url_for('admin_panel'))
        
        # 處理圖片上傳
        full_url, thumb_url = None, None
        if image_file and image_file.filename:
            try:
                full_url, thumb_url = process_and_upload_image(image_file, equipment_id)
                if not full_url or not thumb_url:
                    flash('圖片上傳失敗，但數量更新成功', 'warning')
            except Exception as e:
                print(f"Image upload error: {e}")
                flash('圖片上傳失敗，但數量更新成功', 'warning')
        
        # 更新總數量和可借數量
        new_available_quantity = new_total_quantity - borrowed_quantity
        
        if full_url and thumb_url:
            # 有新圖片，更新圖片 URL
            cursor.execute('''
                UPDATE equipment 
                SET total_quantity = %s, available_quantity = %s, 
                    image_full_url = %s, image_thumb_url = %s
                WHERE id = %s
            ''', (new_total_quantity, new_available_quantity, full_url, thumb_url, equipment_id))
        else:
            # 沒有新圖片，只更新數量
            cursor.execute('''
                UPDATE equipment 
                SET total_quantity = %s, available_quantity = %s 
                WHERE id = %s
            ''', (new_total_quantity, new_available_quantity, equipment_id))
        
        conn.commit()
        flash(f'成功更新 {model_name} 數量為 {new_total_quantity} 件', 'success')
    except Exception as e:
        conn.rollback()
        flash('更新失敗，請稍後再試', 'error')
        print(f"Update equipment error: {e}")
    finally:
        conn.close()
    
    return redirect(url_for('admin_panel'))

@app.route('/add_equipment', methods=['POST'])
@admin_required
def add_equipment():
    category = request.form['category'].strip()
    model = request.form['model'].strip()
    total_quantity = int(request.form['total_quantity'])
    image_file = request.files.get('equipment_image')
    
    if not category or not model or total_quantity < 1:
        flash('請填寫完整且正確的器材資訊', 'error')
        return redirect(url_for('admin_panel'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 檢查是否已存在相同的器材（排除已刪除的）
        cursor.execute('''
            SELECT id FROM equipment 
            WHERE category = %s AND model = %s AND deleted_at IS NULL
        ''', (category, model))
        
        if cursor.fetchone():
            flash(f'器材 {category} - {model} 已存在，請使用修改功能調整數量', 'error')
            conn.close()
            return redirect(url_for('admin_panel'))
        
        # 新增器材
        cursor.execute('''
            INSERT INTO equipment (category, model, total_quantity, available_quantity) 
            VALUES (%s, %s, %s, %s) RETURNING id
        ''', (category, model, total_quantity, total_quantity))
        equipment_id = cursor.fetchone()[0]
        
        conn.commit()
        
        # 處理圖片上傳（如果有的話）
        if image_file and image_file.filename:
            try:
                full_url, thumb_url = process_and_upload_image(image_file, equipment_id)
                if full_url and thumb_url:
                    # 更新器材的圖片 URL
                    cursor.execute('''
                        UPDATE equipment 
                        SET image_full_url = %s, image_thumb_url = %s 
                        WHERE id = %s
                    ''', (full_url, thumb_url, equipment_id))
                    conn.commit()
                    flash(f'成功新增器材：{category} - {model} ({total_quantity} 件) 並上傳圖片', 'success')
                else:
                    flash(f'成功新增器材：{category} - {model} ({total_quantity} 件)，但圖片上傳失敗', 'warning')
            except Exception as e:
                print(f"Image upload error: {e}")
                flash(f'成功新增器材：{category} - {model} ({total_quantity} 件)，但圖片上傳失敗', 'warning')
        else:
            flash(f'成功新增器材：{category} - {model} ({total_quantity} 件)', 'success')
        
    except Exception as e:
        conn.rollback()
        flash('新增失敗，請稍後再試', 'error')
        print(f"Add equipment error: {e}")
    finally:
        conn.close()
    
    return redirect(url_for('admin_panel'))

@app.route('/delete_equipment/<int:equipment_id>')
@admin_required
def delete_equipment(equipment_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 檢查器材是否存在且未被刪除
        cursor.execute('SELECT category, model FROM equipment WHERE id = %s AND deleted_at IS NULL', (equipment_id,))
        equipment = cursor.fetchone()
        
        if not equipment:
            flash('器材不存在或已被刪除', 'error')
            conn.close()
            return redirect(url_for('admin_panel'))
        
        # 檢查是否有未歸還的租借記錄
        cursor.execute('''
            SELECT COUNT(*) FROM rental_records 
            WHERE equipment_id = %s AND status = 'borrowed'
        ''', (equipment_id,))
        
        borrowed_count = cursor.fetchone()[0]
        if borrowed_count > 0:
            flash(f'無法刪除 {equipment[1]}：還有 {borrowed_count} 件未歸還', 'error')
            conn.close()
            return redirect(url_for('admin_panel'))
        
        # 執行軟刪除：設定 deleted_at 時間戳
        current_time = get_taiwan_time()
        cursor.execute('''
            UPDATE equipment 
            SET deleted_at = %s 
            WHERE id = %s
        ''', (current_time, equipment_id))
        
        conn.commit()
        flash(f'成功刪除器材：{equipment[0]} - {equipment[1]}', 'success')
        
        # 可選：刪除圖片（因為器材已經軟刪除）
        try:
            delete_equipment_images(equipment_id)
        except Exception as e:
            print(f"Delete image warning: {e}")
        
    except Exception as e:
        conn.rollback()
        flash('刪除失敗，請稍後再試', 'error')
        print(f"Delete equipment error: {e}")
    finally:
        conn.close()
    
    return redirect(url_for('admin_panel'))

@app.route('/delete_user/<int:user_id>')
@admin_required
def delete_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 檢查用戶是否存在且不是管理員
        cursor.execute('SELECT student_id, name FROM users WHERE id = %s AND is_admin = 0', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            flash('找不到該用戶或無法刪除管理員帳號', 'error')
            conn.close()
            return redirect(url_for('admin_panel'))
        
        # 檢查是否有未歸還的器材
        cursor.execute('''
            SELECT COUNT(*) FROM rental_records 
            WHERE user_id = %s AND status = 'borrowed'
        ''', (user_id,))
        
        unreturned_count = cursor.fetchone()[0]
        if unreturned_count > 0:
            flash(f'無法刪除 {user[1]} ({user[0]})：還有 {unreturned_count} 件器材未歸還', 'error')
            conn.close()
            return redirect(url_for('admin_panel'))
        
        # 刪除用戶（保留租借歷史記錄以供追蹤）
        cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
        
        conn.commit()
        flash(f'成功刪除社員：{user[1]} ({user[0]})', 'success')
    except Exception as e:
        conn.rollback()
        flash('刪除失敗，請稍後再試', 'error')
        print(f"Delete user error: {e}")
    finally:
        conn.close()
    
    return redirect(url_for('admin_panel'))

@app.route('/reset_user_password', methods=['POST'])
@admin_required
def reset_user_password():
    user_id = request.form['user_id']
    new_password = request.form['new_password']
    
    if not new_password or len(new_password) < 4:
        flash('新密碼長度至少需要4個字元', 'error')
        return redirect(url_for('admin_panel'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 檢查用戶是否存在且不是管理員
        cursor.execute('SELECT student_id, name FROM users WHERE id = %s AND is_admin = 0', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            flash('找不到該用戶或無法重設管理員密碼', 'error')
            conn.close()
            return redirect(url_for('admin_panel'))
        
        # 更新密碼
        hashed_password = generate_password_hash(new_password)
        cursor.execute('UPDATE users SET password = %s WHERE id = %s', (hashed_password, user_id))
        
        conn.commit()
        flash(f'成功重設 {user[1]} ({user[0]}) 的密碼', 'success')
    except Exception as e:
        conn.rollback()
        flash('重設密碼失敗，請稍後再試', 'error')
        print(f"Reset password error: {e}")
    finally:
        conn.close()
    
    return redirect(url_for('admin_panel'))

@app.route('/migrate_db')
@admin_required
def migrate_db():
    """手動資料庫遷移 - 添加新欄位"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        migration_success = []
        migration_errors = []
        
        # PostgreSQL 遷移
        try:
            cursor.execute('''
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'rental_records' AND column_name = 'expected_return_date'
            ''')
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE rental_records ADD COLUMN expected_return_date DATE')
                migration_success.append('Added expected_return_date column')
            else:
                migration_success.append('expected_return_date column already exists')
        except Exception as e:
            migration_errors.append(f'expected_return_date: {e}')
        
        try:
            cursor.execute('''
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'rental_records' AND column_name = 'rental_days'
            ''')
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE rental_records ADD COLUMN rental_days INTEGER')
                migration_success.append('Added rental_days column')
            else:
                migration_success.append('rental_days column already exists')
        except Exception as e:
            migration_errors.append(f'rental_days: {e}')
        
        # 圖片欄位遷移
        try:
            cursor.execute('''
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'equipment' AND column_name = 'image_full_url'
            ''')
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE equipment ADD COLUMN image_full_url TEXT')
                migration_success.append('Added image_full_url column')
            else:
                migration_success.append('image_full_url column already exists')
        except Exception as e:
            migration_errors.append(f'image_full_url: {e}')
        
        try:
            cursor.execute('''
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'equipment' AND column_name = 'image_thumb_url'
            ''')
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE equipment ADD COLUMN image_thumb_url TEXT')
                migration_success.append('Added image_thumb_url column')
            else:
                migration_success.append('image_thumb_url column already exists')
        except Exception as e:
            migration_errors.append(f'image_thumb_url: {e}')
        
        # 新增：軟刪除欄位遷移
        try:
            cursor.execute('''
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'equipment' AND column_name = 'deleted_at'
            ''')
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE equipment ADD COLUMN deleted_at TIMESTAMP NULL')
                migration_success.append('Added deleted_at column for soft delete')
            else:
                migration_success.append('deleted_at column already exists')
        except Exception as e:
            migration_errors.append(f'deleted_at: {e}')
        
        conn.commit()
        conn.close()
        
        # 顯示遷移結果
        if migration_success:
            for msg in migration_success:
                flash(f'✅ {msg}', 'success')
        if migration_errors:
            for msg in migration_errors:
                flash(f'❌ {msg}', 'error')
                
        if not migration_errors:
            flash('🎉 資料庫遷移完成！現在可以正常使用圖片和軟刪除功能了', 'success')
        
    except Exception as e:
        flash(f'遷移失敗：{e}', 'error')
        print(f"Migration error: {e}")
    
    return redirect(url_for('admin_panel'))

@app.route('/export_excel')
@admin_required
def export_excel():
    try:
        # 使用 pandas 直接從 PostgreSQL 讀取
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL.replace('postgres://', 'postgresql://', 1))
        
        query = '''
            SELECT u.name as "借用人", u.student_id as "學號", 
                   e.category as "器材類型", e.model as "型號",
                   rr.rental_time as "租借時間", rr.return_time as "歸還時間",
                   CASE WHEN rr.status = 'returned' THEN '已歸還' ELSE '未歸還' END as "狀態"
            FROM rental_records rr
            JOIN users u ON rr.user_id = u.id
            JOIN equipment e ON rr.equipment_id = e.id
            ORDER BY rr.rental_time DESC
        '''
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        # 創建記憶體中的 Excel 檔案
        output = io.BytesIO()
        filename = f'guitar_club_rental_records_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='租借記錄')
        
        output.seek(0)
        
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        flash('匯出失敗，請稍後再試', 'error')
        print(f"Export error: {e}")
        return redirect(url_for('admin_panel'))

# 在程式啟動時初始化資料庫
try:
    with app.app_context():
        ensure_db_initialized()
except:
    @app.before_first_request
    def initialize_database():
        ensure_db_initialized()

if __name__ == '__main__':
    ensure_db_initialized()
    if os.environ.get('RENDER'):
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
    else:
        app.run(debug=True)