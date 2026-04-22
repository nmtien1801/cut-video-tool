"""
config.py — Cấu hình chung toàn app
"""
import os
import sys
import shutil

# --- CÁC HẰNG SỐ CƠ BẢN (Thiếu cái này sẽ bị lỗi ImportError) ---
APP_NAME    = "Creatimic Studio"
APP_VERSION = "2.0.0"

# Thư mục output mặc định
DOWNLOADS_DIR = os.path.join(os.path.expanduser("~"), "Downloads")

# Lấy đường dẫn gốc của dự án (thư mục VIDEO_TOOL)
# Vì file này nằm trong app/, ta lấy cha của nó để tìm thư mục bin/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- LOGIC TÌM BINARY ---

def _find_ffmpeg() -> str:
    # 1. Kiểm tra nếu đã đóng gói bằng PyInstaller (dùng cho lúc xuất file .exe)
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # noqa
        win = os.path.join(base, "ffmpeg.exe")
        if os.path.exists(win):
            return win

    # 2. ƯU TIÊN: Kiểm tra trong thư mục bin/ ở gốc dự án
    local_bin = os.path.join(BASE_DIR, "bin", "ffmpeg.exe")
    if os.path.exists(local_bin):
        return local_bin

    # 3. Tìm trong PATH hệ thống (nếu máy đã cài sẵn)
    found = shutil.which("ffmpeg")
    if found:
        return found

    raise FileNotFoundError(
        "Không tìm thấy ffmpeg. Hãy kiểm tra thư mục bin/ hoặc cài đặt ffmpeg.\n"
        "Windows: https://www.gyan.dev/ffmpeg/builds/"
    )

def _find_ffprobe() -> str:
    # 1. Kiểm tra PyInstaller
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # noqa
        win = os.path.join(base, "ffprobe.exe")
        if os.path.exists(win):
            return win
            
    # 2. ƯU TIÊN: Kiểm tra trong thư mục bin/
    local_bin = os.path.join(BASE_DIR, "bin", "ffprobe.exe")
    if os.path.exists(local_bin):
        return local_bin

    # 3. Tìm trong PATH
    found = shutil.which("ffprobe")
    if found:
        return found
        
    raise FileNotFoundError("Không tìm thấy ffprobe.exe.")

# Thực thi tìm kiếm và gán vào biến hằng số
FFMPEG_BIN  = _find_ffmpeg()
FFPROBE_BIN = _find_ffprobe()