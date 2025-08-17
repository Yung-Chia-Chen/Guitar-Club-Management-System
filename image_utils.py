import os
import io
from PIL import Image, ImageOps
from supabase import create_client, Client
import uuid
from typing import Tuple, Optional

# Supabase 設定
SUPABASE_URL = "https://fzaoayhpvfyjtvslqxsr.supabase.co"
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_KEY')  # 需要設定環境變數
BUCKET_NAME = "equipment-images"

# 建立 Supabase 客戶端
def get_supabase_client():
    """取得 Supabase 客戶端，加入錯誤處理"""
    if not SUPABASE_KEY:
        print("Warning: SUPABASE_SERVICE_KEY not found in environment variables")
        return None
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def process_and_upload_image(file, equipment_id: int) -> Tuple[Optional[str], Optional[str]]:
    """
    處理並上傳圖片到 Supabase Storage
    
    Args:
        file: 上傳的檔案物件 (Flask request.files)
        equipment_id: 器材 ID
    
    Returns:
        Tuple[str, str]: (原圖 URL, 縮圖 URL)
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            print("Supabase client initialization failed")
            return None, None
        
        # 讀取原始圖片
        image_data = file.read()
        file.seek(0)  # 重置檔案指標
        
        # 檢查檔案大小 (5MB 限制)
        if len(image_data) > 5 * 1024 * 1024:
            raise ValueError("檔案大小超過 5MB 限制")
        
        # 開啟圖片
        original_image = Image.open(io.BytesIO(image_data))
        
        # 轉換為 RGB (處理 RGBA 和其他格式)
        if original_image.mode in ('RGBA', 'LA'):
            # 建立白色背景
            background = Image.new('RGB', original_image.size, (255, 255, 255))
            if original_image.mode == 'RGBA':
                background.paste(original_image, mask=original_image.split()[-1])
            else:
                background.paste(original_image, mask=original_image.split()[-1])
            original_image = background
        elif original_image.mode != 'RGB':
            original_image = original_image.convert('RGB')
        
        # 自動修正圖片方向 (處理手機拍照旋轉問題)
        original_image = ImageOps.exif_transpose(original_image)
        
        # 處理原圖 (最大寬度 1200px)
        full_image = resize_image(original_image, max_width=1200)
        full_image_data = image_to_bytes(full_image, quality=85)
        
        # 處理縮圖 (60x60px 正方形)
        thumb_image = create_square_thumbnail(original_image, size=60)
        thumb_image_data = image_to_bytes(thumb_image, quality=80)
        
        # 上傳到 Supabase Storage
        full_filename = f"equipment_{equipment_id}_full.jpg"
        thumb_filename = f"equipment_{equipment_id}_thumb.jpg"
        
        # 刪除舊圖片 (如果存在)
        delete_existing_images(equipment_id)
        
        # 上傳新圖片
        full_url = upload_to_supabase(full_image_data, full_filename)
        thumb_url = upload_to_supabase(thumb_image_data, thumb_filename)
        
        return full_url, thumb_url
        
    except Exception as e:
        print(f"圖片處理錯誤: {e}")
        return None, None

def resize_image(image: Image.Image, max_width: int) -> Image.Image:
    """
    等比例縮放圖片，限制最大寬度
    """
    if image.width <= max_width:
        return image
    
    # 計算新的高度，保持比例
    ratio = max_width / image.width
    new_height = int(image.height * ratio)
    
    return image.resize((max_width, new_height), Image.Resampling.LANCZOS)

def create_square_thumbnail(image: Image.Image, size: int) -> Image.Image:
    """
    建立正方形縮圖，使用智慧裁切 (中心裁切)
    """
    # 獲取原圖尺寸
    width, height = image.size
    
    # 計算裁切區域 (保持中心)
    if width > height:
        # 橫向圖片，裁切左右
        left = (width - height) // 2
        right = left + height
        crop_box = (left, 0, right, height)
    else:
        # 縱向圖片，裁切上下
        top = (height - width) // 2
        bottom = top + width
        crop_box = (0, top, width, bottom)
    
    # 裁切成正方形
    square_image = image.crop(crop_box)
    
    # 縮放到目標大小
    return square_image.resize((size, size), Image.Resampling.LANCZOS)

def image_to_bytes(image: Image.Image, quality: int = 85) -> bytes:
    """
    將 PIL Image 轉換為 bytes
    """
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='JPEG', quality=quality, optimize=True)
    return img_byte_arr.getvalue()

def upload_to_supabase(image_data: bytes, filename: str) -> Optional[str]:
    """
    上傳圖片到 Supabase Storage
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            return None
        
        # 上傳檔案
        result = supabase.storage.from_(BUCKET_NAME).upload(
            filename, 
            image_data,
            file_options={"content-type": "image/jpeg", "upsert": "true"}
        )
        
        if hasattr(result, 'error') and result.error:
            print(f"上傳錯誤: {result.error}")
            return None
        
        # 取得公開 URL
        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(filename)
        return public_url
        
    except Exception as e:
        print(f"Supabase 上傳錯誤: {e}")
        return None

def delete_existing_images(equipment_id: int):
    """
    刪除器材的現有圖片
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            return
        
        full_filename = f"equipment_{equipment_id}_full.jpg"
        thumb_filename = f"equipment_{equipment_id}_thumb.jpg"
        
        # 嘗試刪除 (如果檔案不存在也不會錯誤)
        supabase.storage.from_(BUCKET_NAME).remove([full_filename, thumb_filename])
        
    except Exception as e:
        print(f"刪除舊圖片警告: {e}")

def delete_equipment_images(equipment_id: int) -> bool:
    """
    刪除器材的所有圖片 (用於刪除器材時)
    """
    try:
        delete_existing_images(equipment_id)
        return True
    except Exception as e:
        print(f"刪除器材圖片錯誤: {e}")
        return False

def get_image_urls(equipment_id: int) -> Tuple[Optional[str], Optional[str]]:
    """
    取得器材圖片的 URL
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            return None, None
        
        full_filename = f"equipment_{equipment_id}_full.jpg"
        thumb_filename = f"equipment_{equipment_id}_thumb.jpg"
        
        # 檢查檔案是否存在
        full_exists = check_file_exists(full_filename)
        thumb_exists = check_file_exists(thumb_filename)
        
        full_url = None
        thumb_url = None
        
        if full_exists:
            full_url = supabase.storage.from_(BUCKET_NAME).get_public_url(full_filename)
        
        if thumb_exists:
            thumb_url = supabase.storage.from_(BUCKET_NAME).get_public_url(thumb_filename)
        
        return full_url, thumb_url
        
    except Exception as e:
        print(f"取得圖片 URL 錯誤: {e}")
        return None, None

def check_file_exists(filename: str) -> bool:
    """
    檢查檔案是否存在於 Supabase Storage
    """
    try:
        supabase = get_supabase_client()
        if not supabase:
            return False
        
        result = supabase.storage.from_(BUCKET_NAME).list()
        if hasattr(result, 'error') and result.error:
            return False
        
        # 檢查檔案列表中是否包含指定檔案
        file_list = [file['name'] for file in result if file['name'] == filename]
        return len(file_list) > 0
        
    except Exception as e:
        print(f"檢查檔案存在錯誤: {e}")
        return False