# 🎸 吉他社管理系統

一個現代化的吉他社器材租借管理系統，使用 Flask + PostgreSQL 構建，部署在 Render 平台上。

## 📋 功能特色

### 🔐 用戶管理
- **會員註冊與登入系統**
- **角色權限管理**（一般用戶 / 管理員）
- **密碼加密存儲**（使用 Werkzeug）
- **管理員可重設用戶密碼**

### 🎸 器材管理
- **多類型器材支援**（插電吉他、不插電吉他、控台、喇叭等）
- **庫存數量管理**
- **器材狀態追蹤**（可借 / 已借完 / 庫存不足）
- **動態器材新增 / 修改 / 刪除**

### 📝 租借系統
- **批次租借**（可同時借用多件器材）
- **分批歸還**（支援部分歸還器材）
- **先借先還原則**
- **即時庫存更新**

### 📊 管理介面
- **詳細租借記錄**（區分初始租借和歸還記錄）
- **未歸還器材追蹤**
- **借用天數計算**
- **會員管理功能**
- **Excel 報表匯出**

### 🎨 用戶體驗
- **響應式設計**（支援桌面和行動裝置）
- **直觀的視覺化狀態**
- **即時表單驗證**
- **友善的錯誤提示**

## 🛠 技術架構

### 後端技術
- **Flask 2.3.3** - Python Web 框架
- **PostgreSQL** - 主要資料庫（Supabase 託管）
- **SQLite** - 本地開發備用
- **psycopg2** - PostgreSQL 驅動程式
- **Werkzeug** - 密碼加密

### 前端技術
- **Bootstrap 5.1.3** - CSS 框架
- **Font Awesome 6.0.0** - 圖標庫
- **JavaScript** - 動態互動功能

### 部署架構
- **Render** - 應用程式託管平台
- **Supabase** - PostgreSQL 資料庫託管
- **Git** - 版本控制

## 🚀 部署指南

### 📋 環境要求
- Python 3.8+
- PostgreSQL 12+ 或 SQLite 3
- Git

### 🔧 本地開發設定

1. **克隆專案**
```bash
git clone <your-repository-url>
cd guitar-club-management-system
```

2. **安裝依賴**
```bash
pip install -r requirements.txt
```

3. **環境變數設定**
創建 `.env` 檔案：
```bash
DATABASE_URL=postgresql://user:password@host:port/database
SECRET_KEY=your-secret-key-here
```

4. **執行應用程式**
```bash
python app.py
```

### ☁️ Render 部署

1. **連接 GitHub**
   - 在 Render Dashboard 創建新的 Web Service
   - 連接你的 GitHub repository

2. **環境變數設定**
   ```
   DATABASE_URL=your-supabase-connection-string
   SECRET_KEY=your-random-secret-key
   ```

3. **自動部署**
   - 推送代碼到 main 分支即可自動部署

### 🗄️ Supabase 資料庫設定

1. **創建專案**
   - 前往 [supabase.com](https://supabase.com)
   - 創建新專案，選擇 Southeast Asia (Singapore) 區域

2. **取得連接字串**
   - 進入 Settings → Database
   - 複製 Session pooler 連接字串
   - 格式：`postgresql://postgres.xxx:password@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres`

## 📊 資料庫結構

### 👤 Users 表
- `id` - 主鍵
- `student_id` - 學號（唯一）
- `name` - 姓名
- `class_name` - 班級
- `club_role` - 社團身分
- `password` - 加密密碼
- `is_admin` - 管理員標記
- `created_at` - 註冊時間

### 🎸 Equipment 表
- `id` - 主鍵
- `category` - 器材類型
- `model` - 型號
- `total_quantity` - 總數量
- `available_quantity` - 可借數量

### 📝 Rental_Records 表
- `id` - 主鍵
- `user_id` - 用戶ID（外鍵）
- `equipment_id` - 器材ID（外鍵）
- `rental_time` - 租借時間
- `return_time` - 歸還時間
- `status` - 狀態（borrowed/returned）

## 🎯 預設資料

### 管理員帳號
- **學號**：`admin`
- **密碼**：`admin123`
- **角色**：系統管理員

### 預設器材
- 插電吉他：Fender Stratocaster (2), Ibanez RG (3), Gibson Les Paul (1)
- 不插電吉他：Yamaha FG830 (4), Martin D-28 (1), Taylor 814ce (2)
- 控台：Behringer X32 (1), Yamaha MG16XU (2)
- 喇叭：JBL EON615 (3), Yamaha DBR15 (2)

## 🔧 主要功能說明

### 租借流程
1. 用戶登入系統
2. 選擇器材類別和型號
3. 選擇借用數量
4. 系統自動更新庫存
5. 記錄租借時間

### 歸還流程
1. 選擇要歸還的器材
2. 選擇歸還數量（支援分批歸還）
3. 系統按先借先還原則處理
4. 自動更新庫存和記錄

### 管理功能
- **器材庫存管理**：新增、修改、刪除器材
- **會員管理**：查看會員、重設密碼、刪除帳號
- **租借記錄**：詳細的借還歷史追蹤
- **Excel 匯出**：完整的租借記錄報表

## 🎨 界面特色

- **統一配色**：租借記錄使用深藍色背景，歸還記錄使用白色背景
- **狀態標籤**：直觀的彩色標籤顯示器材和租借狀態
- **響應式設計**：適配各種螢幕尺寸
- **即時反饋**：操作成功/失敗的即時提示

## 🔒 安全特性

- **密碼加密**：使用 Werkzeug 進行密碼雜湊
- **Session 管理**：安全的用戶會話處理
- **權限控制**：管理員和一般用戶權限分離
- **SQL 注入防護**：使用參數化查詢
- **HTTPS 連接**：生產環境強制 SSL

## 📈 系統監控

### 健康檢查
- **端點**：`/health`
- **回應**：系統狀態、時間戳、資料庫類型

### 效能特色
- **連接池**：使用 Supabase 連接池優化資料庫連接
- **索引優化**：主鍵和外鍵自動索引
- **查詢優化**：使用 CTE 優化複雜查詢

## 🐛 故障排除

### 常見問題

**1. 資料庫連接失敗**
- 檢查 `DATABASE_URL` 格式是否正確
- 確認 Supabase 專案是否運行中
- 使用 Session pooler 而非 Direct connection

**2. 部署失敗**
- 檢查 `requirements.txt` 是否包含所有依賴
- 確認環境變數設定正確
- 查看 Render 部署日誌

**3. 功能異常**
- 檢查瀏覽器控制台錯誤
- 確認 JavaScript 正常載入
- 查看 Flask 應用程式日誌

## 🔄 更新記錄

### v2.0.0 (2025-07-25)
- ✅ 遷移到 PostgreSQL + Supabase
- ✅ 新增批次租借和分批歸還功能
- ✅ 優化管理介面和記錄顯示
- ✅ 統一租借記錄視覺樣式
- ✅ 改善查詢效能和錯誤處理

### v1.0.0 (初始版本)
- ✅ 基本租借管理功能
- ✅ 用戶註冊和登入系統
- ✅ SQLite 資料庫支援

## 🤝 貢獻指南

1. Fork 專案
2. 創建功能分支 (`git checkout -b feature/new-feature`)
3. 提交變更 (`git commit -am 'Add new feature'`)
4. 推送分支 (`git push origin feature/new-feature`)
5. 創建 Pull Request


## 📧 聯絡資訊

如有問題或建議，請透過以下方式聯絡：

- 📧 **電子郵件**：Joe081488@gmail.com

---

**🎸 感謝使用吉他社管理系統！**
