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

app = Flask(__name__)

# 生產環境配置
if os.environ.get('RENDER'):
    app.secret_key = os.environ.get('SECRET_KEY', 'fallback-secret-key-change-me')
    DATABASE_URL = os.environ.get('DATABASE_URL')
else:
    app.secret_key = 'your-secret-key-here'
    # 本地開發時，你可以設定本地 PostgreSQL 或使用 SQLite 替代
    DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///guitar_club.db')

# 設定台灣時區
TW_TZ = pytz.timezone('Asia/Taipei')

def get_taiwan_time():
    """取得台灣當前時間"""
    return datetime.now(TW_TZ).strftime('%Y-%m-%d %H:%M:%S')

def get_db_connection():
    """取得資料庫連接"""
    if DATABASE_URL.startswith('postgresql://') or DATABASE_URL.startswith('postgres://'):
        # PostgreSQL 連接
        # 修正 postgres:// 為 postgresql:// (某些版本需要)
        db_url = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
        conn = psycopg2.connect(db_url)
        conn.autocommit = False  # 手動控制事務
        return conn
    else:
        # SQLite 連接（向後相容，本地開發用）
        import sqlite3
        conn = sqlite3.connect(DATABASE_URL.replace('sqlite:///', ''))
        return conn

def is_postgresql():
    """檢查是否使用 PostgreSQL"""
    return DATABASE_URL.startswith('postgresql://') or DATABASE_URL.startswith('postgres://')

# 資料庫初始化
def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if is_postgresql():
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
            
            # 創建器材表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS equipment (
                    id SERIAL PRIMARY KEY,
                    category VARCHAR(100) NOT NULL,
                    model VARCHAR(200) NOT NULL,
                    total_quantity INTEGER NOT NULL DEFAULT 1,
                    available_quantity INTEGER NOT NULL DEFAULT 1
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
                    status VARCHAR(20) DEFAULT 'borrowed',
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (equipment_id) REFERENCES equipment (id)
                )
            ''')
        else:
            # SQLite 版本（保持原有邏輯）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    class_name TEXT NOT NULL,
                    club_role TEXT NOT NULL,
                    password TEXT NOT NULL,
                    is_admin INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS equipment (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    model TEXT NOT NULL,
                    total_quantity INTEGER NOT NULL DEFAULT 1,
                    available_quantity INTEGER NOT NULL DEFAULT 1
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS rental_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    equipment_id INTEGER NOT NULL,
                    rental_time TEXT NOT NULL,
                    return_time TEXT NULL,
                    status TEXT DEFAULT 'borrowed',
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    FOREIGN KEY (equipment_id) REFERENCES equipment (id)
                )
            ''')
        
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
        
        cursor.execute('SELECT COUNT(*) FROM equipment')
        if cursor.fetchone()[0] == 0:
            if is_postgresql():
                cursor.executemany(
                    'INSERT INTO equipment (category, model, total_quantity, available_quantity) VALUES (%s, %s, %s, %s)', 
                    [(item[0], item[1], item[2], item[2]) for item in equipment_data]
                )
            else:
                cursor.executemany(
                    'INSERT INTO equipment (category, model, total_quantity, available_quantity) VALUES (?, ?, ?, ?)', 
                    [(item[0], item[1], item[2], item[2]) for item in equipment_data]
                )
        
        # 創建預設管理員帳號
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
        if cursor.fetchone()[0] == 0:
            admin_password = generate_password_hash('admin123')
            admin_created_time = get_taiwan_time()
            if is_postgresql():
                cursor.execute('''
                    INSERT INTO users (student_id, name, class_name, club_role, password, is_admin, created_at) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', ('admin', '系統管理員', '管理組', '系統管理員', admin_password, 1, admin_created_time))
            else:
                cursor.execute('''
                    INSERT INTO users (student_id, name, class_name, club_role, password, is_admin, created_at) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', ('admin', '系統管理員', '管理組', '系統管理員', admin_password, 1, admin_created_time))
        
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

# 統一的查詢執行函數
def execute_query(query, params=None, fetch=None):
    """統一的查詢執行函數，自動處理 PostgreSQL 和 SQLite 的差異"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if is_postgresql():
            # PostgreSQL 使用 %s 佔位符
            if params:
                pg_query = query.replace('?', '%s')
                cursor.execute(pg_query, params)
            else:
                cursor.execute(query)
        else:
            # SQLite 使用 ? 佔位符
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
        
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
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# 管理員檢查裝飾器
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ensure_db_initialized()
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        user = execute_query('SELECT is_admin FROM users WHERE id = ?', (session['user_id'],), fetch='one')
        
        if not user or not user[0]:
            flash('需要管理員權限', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    ensure_db_initialized()
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/health')
def health_check():
    ensure_db_initialized()
    return {
        'status': 'healthy', 
        'timestamp': get_taiwan_time(),
        'message': 'Guitar Club System is running',
        'database': 'PostgreSQL' if is_postgresql() else 'SQLite'
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
                VALUES (?, ?, ?, ?, ?, ?)
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    ensure_db_initialized()
    if request.method == 'POST':
        student_id = request.form['student_id']
        password = request.form['password']
        
        user = execute_query('SELECT id, name, password, is_admin FROM users WHERE student_id = ?', (student_id,), fetch='one')
        
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['user_name'] = user[1]
            session['is_admin'] = user[3]
            
            flash(f'歡迎回來，{user[1]}！', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('學號或密碼錯誤', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('已登出', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 取得器材類別
    cursor.execute('SELECT DISTINCT category FROM equipment')
    categories = [row[0] for row in cursor.fetchall()]
    
    # 取得用戶的租借記錄（按時間和器材分組）
    if is_postgresql():
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
    else:
        cursor.execute('''
            SELECT rr.rental_time, e.category, e.model, 
                   COUNT(*) as quantity,
                   MAX(rr.id) as latest_id,
                   SUM(CASE WHEN rr.status = 'borrowed' THEN 1 ELSE 0 END) as borrowed_count,
                   MIN(rr.return_time) as first_return_time,
                   MAX(rr.return_time) as last_return_time
            FROM rental_records rr
            JOIN equipment e ON rr.equipment_id = e.id
            WHERE rr.user_id = ?
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
    models = execute_query('''
        SELECT id, model, available_quantity, total_quantity 
        FROM equipment 
        WHERE category = ? AND available_quantity > 0
    ''', (category,), fetch='all')
    
    return {'models': [
        {
            'id': model[0], 
            'name': f"{model[1]} (可借: {model[2]}/{model[3]})",
            'available': model[2]
        } for model in models
    ]}

@app.route('/borrow_equipment', methods=['POST'])
@login_required
def borrow_equipment():
    equipment_id = request.form['equipment_id']
    borrow_quantity = int(request.form.get('borrow_quantity', 1))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 檢查器材是否可用
        if is_postgresql():
            cursor.execute('''
                SELECT model, available_quantity 
                FROM equipment 
                WHERE id = %s AND available_quantity >= %s
            ''', (equipment_id, borrow_quantity))
        else:
            cursor.execute('''
                SELECT model, available_quantity 
                FROM equipment 
                WHERE id = ? AND available_quantity >= ?
            ''', (equipment_id, borrow_quantity))
        
        equipment = cursor.fetchone()
        
        if not equipment:
            flash('器材庫存不足或不存在', 'error')
            conn.close()
            return redirect(url_for('dashboard'))
        
        # 批量記錄租借（每件器材一筆記錄）
        current_time = get_taiwan_time()
        for i in range(borrow_quantity):
            if is_postgresql():
                cursor.execute('''
                    INSERT INTO rental_records (user_id, equipment_id, rental_time) 
                    VALUES (%s, %s, %s)
                ''', (session['user_id'], equipment_id, current_time))
            else:
                cursor.execute('''
                    INSERT INTO rental_records (user_id, equipment_id, rental_time) 
                    VALUES (?, ?, ?)
                ''', (session['user_id'], equipment_id, current_time))
        
        # 減少可用數量
        if is_postgresql():
            cursor.execute('''
                UPDATE equipment 
                SET available_quantity = available_quantity - %s 
                WHERE id = %s
            ''', (borrow_quantity, equipment_id))
        else:
            cursor.execute('''
                UPDATE equipment 
                SET available_quantity = available_quantity - ? 
                WHERE id = ?
            ''', (borrow_quantity, equipment_id))
        
        conn.commit()
        
        quantity_text = f'{borrow_quantity} 件' if borrow_quantity > 1 else '1 件'
        flash(f'成功借用 {equipment[0]} {quantity_text}', 'success')
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
            if is_postgresql():
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
                    WHERE rr.user_id = ? AND rr.rental_time = ? 
                          AND e.category = ? AND e.model = ? AND rr.status = 'borrowed'
                    ORDER BY rr.id
                ''', (session['user_id'], rental_time, equipment_category, equipment_model))
        else:
            if is_postgresql():
                cursor.execute('''
                    SELECT rr.id 
                    FROM rental_records rr
                    JOIN equipment e ON rr.equipment_id = e.id
                    WHERE rr.user_id = %s AND e.category = %s AND e.model = %s AND rr.status = 'borrowed'
                    ORDER BY rr.rental_time ASC, rr.id ASC
                ''', (session['user_id'], equipment_category, equipment_model))
            else:
                cursor.execute('''
                    SELECT rr.id 
                    FROM rental_records rr
                    JOIN equipment e ON rr.equipment_id = e.id
                    WHERE rr.user_id = ? AND e.category = ? AND e.model = ? AND rr.status = 'borrowed'
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
            if is_postgresql():
                cursor.execute('''
                    UPDATE rental_records 
                    SET return_time = %s, status = 'returned' 
                    WHERE id = %s
                ''', (return_time, record[0]))
            else:
                cursor.execute('''
                    UPDATE rental_records 
                    SET return_time = ?, status = 'returned' 
                    WHERE id = ?
                ''', (return_time, record[0]))
        
        # 更新器材可用數量
        equipment_ids_to_update = set()
        for record in records_to_return:
            # 找出這個記錄對應的器材ID
            if is_postgresql():
                cursor.execute('SELECT equipment_id FROM rental_records WHERE id = %s', (record[0],))
            else:
                cursor.execute('SELECT equipment_id FROM rental_records WHERE id = ?', (record[0],))
            equipment_id = cursor.fetchone()[0]
            equipment_ids_to_update.add(equipment_id)
        
        # 為每個器材增加歸還的數量
        for equipment_id in equipment_ids_to_update:
            # 計算這個器材在這批歸還中的數量
            equipment_return_count = 0
            for record in records_to_return:
                if is_postgresql():
                    cursor.execute('SELECT equipment_id FROM rental_records WHERE id = %s', (record[0],))
                else:
                    cursor.execute('SELECT equipment_id FROM rental_records WHERE id = ?', (record[0],))
                if cursor.fetchone()[0] == equipment_id:
                    equipment_return_count += 1
            
            if is_postgresql():
                cursor.execute('''
                    UPDATE equipment 
                    SET available_quantity = available_quantity + %s 
                    WHERE id = %s
                ''', (equipment_return_count, equipment_id))
            else:
                cursor.execute('''
                    UPDATE equipment 
                    SET available_quantity = available_quantity + ? 
                    WHERE id = ?
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
        
        # 取得所有租借記錄（修復 PostgreSQL GROUP BY 問題）
        if is_postgresql():
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
                    FROM rental_records
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
        else:
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
                    FROM rental_records
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
                         CASE WHEN return_time IS NULL THEN '9999-12-31 23:59:59' ELSE return_time END DESC
                LIMIT 100
            ''')
        all_rentals = cursor.fetchall()
        
        # 取得未歸還的器材
        if is_postgresql():
            cursor.execute('''
                SELECT u.name, u.student_id, e.category, e.model, 
                       COUNT(*) as total_borrowed_count,
                       MIN(rr.rental_time) as first_rental_time,
                       MAX(rr.rental_time) as last_rental_time
                FROM rental_records rr
                JOIN users u ON rr.user_id = u.id
                JOIN equipment e ON rr.equipment_id = e.id
                WHERE rr.status = 'borrowed'
                GROUP BY u.id, e.id, u.name, u.student_id, e.category, e.model
                ORDER BY first_rental_time ASC
            ''')
        else:
            cursor.execute('''
                SELECT u.name, u.student_id, e.category, e.model, 
                       COUNT(*) as total_borrowed_count,
                       MIN(rr.rental_time) as first_rental_time,
                       MAX(rr.rental_time) as last_rental_time
                FROM rental_records rr
                JOIN users u ON rr.user_id = u.id
                JOIN equipment e ON rr.equipment_id = e.id
                WHERE rr.status = 'borrowed'
                GROUP BY u.id, e.id
                ORDER BY first_rental_time ASC
            ''')
        unreturned = cursor.fetchall()
        
        # 取得器材庫存狀況
        cursor.execute('''
            SELECT e.id, e.category, e.model, e.total_quantity, e.available_quantity,
                   (e.total_quantity - e.available_quantity) as borrowed_quantity
            FROM equipment e
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
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 取得目前器材資訊
        if is_postgresql():
            cursor.execute('''
                SELECT total_quantity, available_quantity, model 
                FROM equipment WHERE id = %s
            ''', (equipment_id,))
        else:
            cursor.execute('''
                SELECT total_quantity, available_quantity, model 
                FROM equipment WHERE id = ?
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
        
        # 更新總數量和可借數量
        new_available_quantity = new_total_quantity - borrowed_quantity
        if is_postgresql():
            cursor.execute('''
                UPDATE equipment 
                SET total_quantity = %s, available_quantity = %s 
                WHERE id = %s
            ''', (new_total_quantity, new_available_quantity, equipment_id))
        else:
            cursor.execute('''
                UPDATE equipment 
                SET total_quantity = ?, available_quantity = ? 
                WHERE id = ?
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
    
    if not category or not model or total_quantity < 1:
        flash('請填寫完整且正確的器材資訊', 'error')
        return redirect(url_for('admin_panel'))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 檢查是否已存在相同的器材
        if is_postgresql():
            cursor.execute('''
                SELECT id FROM equipment 
                WHERE category = %s AND model = %s
            ''', (category, model))
        else:
            cursor.execute('''
                SELECT id FROM equipment 
                WHERE category = ? AND model = ?
            ''', (category, model))
        
        if cursor.fetchone():
            flash(f'器材 {category} - {model} 已存在，請使用修改功能調整數量', 'error')
            conn.close()
            return redirect(url_for('admin_panel'))
        
        # 新增器材
        if is_postgresql():
            cursor.execute('''
                INSERT INTO equipment (category, model, total_quantity, available_quantity) 
                VALUES (%s, %s, %s, %s)
            ''', (category, model, total_quantity, total_quantity))
        else:
            cursor.execute('''
                INSERT INTO equipment (category, model, total_quantity, available_quantity) 
                VALUES (?, ?, ?, ?)
            ''', (category, model, total_quantity, total_quantity))
        
        conn.commit()
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
        # 檢查是否有未歸還的租借記錄
        if is_postgresql():
            cursor.execute('''
                SELECT COUNT(*) FROM rental_records 
                WHERE equipment_id = %s AND status = 'borrowed'
            ''', (equipment_id,))
        else:
            cursor.execute('''
                SELECT COUNT(*) FROM rental_records 
                WHERE equipment_id = ? AND status = 'borrowed'
            ''', (equipment_id,))
        
        borrowed_count = cursor.fetchone()[0]
        if borrowed_count > 0:
            if is_postgresql():
                cursor.execute('SELECT model FROM equipment WHERE id = %s', (equipment_id,))
            else:
                cursor.execute('SELECT model FROM equipment WHERE id = ?', (equipment_id,))
            model_name = cursor.fetchone()[0]
            flash(f'無法刪除 {model_name}：還有 {borrowed_count} 件未歸還', 'error')
            conn.close()
            return redirect(url_for('admin_panel'))
        
        # 取得器材名稱用於顯示
        if is_postgresql():
            cursor.execute('SELECT category, model FROM equipment WHERE id = %s', (equipment_id,))
        else:
            cursor.execute('SELECT category, model FROM equipment WHERE id = ?', (equipment_id,))
        equipment = cursor.fetchone()
        
        if equipment:
            # 刪除器材
            if is_postgresql():
                cursor.execute('DELETE FROM equipment WHERE id = %s', (equipment_id,))
            else:
                cursor.execute('DELETE FROM equipment WHERE id = ?', (equipment_id,))
            conn.commit()
            flash(f'成功刪除器材：{equipment[0]} - {equipment[1]}', 'success')
        else:
            flash('器材不存在', 'error')
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
        if is_postgresql():
            cursor.execute('SELECT student_id, name FROM users WHERE id = %s AND is_admin = 0', (user_id,))
        else:
            cursor.execute('SELECT student_id, name FROM users WHERE id = ? AND is_admin = 0', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            flash('找不到該用戶或無法刪除管理員帳號', 'error')
            conn.close()
            return redirect(url_for('admin_panel'))
        
        # 檢查是否有未歸還的器材
        if is_postgresql():
            cursor.execute('''
                SELECT COUNT(*) FROM rental_records 
                WHERE user_id = %s AND status = 'borrowed'
            ''', (user_id,))
        else:
            cursor.execute('''
                SELECT COUNT(*) FROM rental_records 
                WHERE user_id = ? AND status = 'borrowed'
            ''', (user_id,))
        
        unreturned_count = cursor.fetchone()[0]
        if unreturned_count > 0:
            flash(f'無法刪除 {user[1]} ({user[0]})：還有 {unreturned_count} 件器材未歸還', 'error')
            conn.close()
            return redirect(url_for('admin_panel'))
        
        # 刪除用戶（保留租借歷史記錄以供追蹤）
        if is_postgresql():
            cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
        else:
            cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        
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
        if is_postgresql():
            cursor.execute('SELECT student_id, name FROM users WHERE id = %s AND is_admin = 0', (user_id,))
        else:
            cursor.execute('SELECT student_id, name FROM users WHERE id = ? AND is_admin = 0', (user_id,))
        user = cursor.fetchone()
        
        if not user:
            flash('找不到該用戶或無法重設管理員密碼', 'error')
            conn.close()
            return redirect(url_for('admin_panel'))
        
        # 更新密碼
        hashed_password = generate_password_hash(new_password)
        if is_postgresql():
            cursor.execute('UPDATE users SET password = %s WHERE id = %s', (hashed_password, user_id))
        else:
            cursor.execute('UPDATE users SET password = ? WHERE id = ?', (hashed_password, user_id))
        
        conn.commit()
        flash(f'成功重設 {user[1]} ({user[0]}) 的密碼', 'success')
    except Exception as e:
        conn.rollback()
        flash('重設密碼失敗，請稍後再試', 'error')
        print(f"Reset password error: {e}")
    finally:
        conn.close()
    
    return redirect(url_for('admin_panel'))

@app.route('/export_excel')
@admin_required
def export_excel():
    try:
        if is_postgresql():
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
        else:
            # SQLite 版本
            import sqlite3
            conn = sqlite3.connect(DATABASE_URL.replace('sqlite:///', ''))
            
            query = '''
                SELECT u.name as '借用人', u.student_id as '學號', 
                       e.category as '器材類型', e.model as '型號',
                       rr.rental_time as '租借時間', rr.return_time as '歸還時間',
                       CASE WHEN rr.status = 'returned' THEN '已歸還' ELSE '未歸還' END as '狀態'
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