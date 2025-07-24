# 🎸 吉他社管理系統

一個基於 Flask 的吉他社器材租借管理系統，支援器材庫存管理、會員管理、租借記錄追蹤等功能。


## ✨ 功能特色

### 👥 會員功能
- 📝 會員註冊與登入
- 🎯 器材租借與歸還
- 📊 個人租借記錄查看
- 🔢 支援多數量租借
- 🎮 分批歸還功能

### 🛠️ 管理員功能
- 📦 器材庫存管理
- ➕ 新增/修改/刪除器材
- 👨‍💼 會員管理
- 🔑 重設會員密碼
- 🗑️ 刪除會員帳號
- 📈 租借記錄統計
- 📄 Excel 報表匯出

### 🎯 系統特色
- 📱 響應式設計，支援手機瀏覽
- 🔒 安全的密碼加密
- ⏰ 台灣時區時間顯示
- 📊 即時庫存更新
- 🔄 分批租借/歸還機制

## 🏗️ 技術架構

- **後端**: Python Flask
- **資料庫**: SQLite
- **前端**: Bootstrap 5 + Font Awesome
- **部署**: Render
- **版本控制**: Git + GitHub

## 📦 安裝與運行

### 本地開發環境

1. **複製專案**
   ```bash
   git clone https://github.com/Yung-Chia-Chen/Guitar-Club-Management-System.git
   cd guitar-club-system
   ```

2. **建立虛擬環境**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

3. **安裝依賴**
   ```bash
   pip install -r requirements.txt
   ```

4. **運行程式**
   ```bash
   python app.py
   ```

5. **開啟瀏覽器**
   - 網址: http://localhost:5000
   - 管理員: `admin` / `admin123`

## 🚀 雲端部署

### Render 部署步驟

1. **Fork 此專案到你的 GitHub**

2. **在 Render 創建 Web Service**
   - 連接 GitHub 倉庫
   - 設定建置指令: `pip install -r requirements.txt`
   - 設定啟動指令: `gunicorn --bind 0.0.0.0:$PORT app:app`

3. **設定環境變數**
   ```
   SECRET_KEY = [生成一個安全的密鑰]
   RENDER = true
   ```

4. **完成部署**
   - 自動創建資料庫和預設資料

## 📊 系統截圖

### 會員功能
- 🏠 **主頁**: 器材租借和歸還界面
- 📝 **註冊**: 學號、姓名、班級、社團身分
- 🔐 **登入**: 安全的會員認證

### 管理功能
- 📦 **器材庫存**: 即時庫存狀態和管理
- 👥 **會員管理**: 會員列表和帳號管理
- 📈 **租借記錄**: 完整的借還歷史追蹤

## 🎯 使用說明

### 👤 一般會員
1. **註冊帳號**: 填寫學號、姓名、班級、社團身分
2. **登入系統**: 使用學號和密碼登入
3. **租借器材**: 選擇類別 → 型號 → 數量
4. **歸還器材**: 在歸還區域選擇要歸還的器材和數量

### 👨‍💼 管理員
1. **器材管理**: 新增器材、調整數量、刪除器材
2. **會員管理**: 查看會員資料、重設密碼、刪除帳號
3. **記錄查看**: 監控租借狀況、查看未歸還器材
4. **資料匯出**: 匯出完整的 Excel 租借報表

## 🔧 系統需求

- **Python**: 3.9+
- **瀏覽器**: Chrome、Firefox、Safari、Edge（支援 ES6）
- **網路**: 需要網路連線以載入 CDN 資源

## 👨‍💻 開發者

- **專案維護**: [Yung-Chia Chen](https://github.com/Yung-Chia-Chen)
- **聯絡方式**: Joe081488@gmail.com

## 🙏 致謝

- Flask 開發團隊
- Render 雲端平台

---

