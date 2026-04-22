video_tool/
│
├── app/
│   ├── __init__.py
│   ├── main.py                  # entry point (chạy app)
│   ├── config.py                # config chung
│
│   ├── core/                    # logic lõi (auth, state)
│   │   ├── __init__.py
│   │   ├── auth.py              # login logic
│   │   └── session.py           # lưu trạng thái login
│
│   ├── services/                # xử lý nghiệp vụ
│   │   ├── __init__.py
│   │   ├── ffmpeg_service.py
│   │   └── video_service.py
│
│   ├── ui/                      # giao diện
│   │   ├── __init__.py
│   │   ├── login_view.py        # màn hình login
│   │   └── dashboard_view.py    # màn hình chính
│
│   ├── utils/
│   │   ├── __init__.py
│   │   └── file_picker.py
│
│   └── models/
│       ├── __init__.py
│       └── user.py
│
├── assets/                      # icon, logo (optional)
├── bin/                      #  ffmpeg.exe
├── requirements.txt
└── README.md



## Tài khoản demo
 
| Tên đăng nhập | Mật khẩu |
|---|---|
| admin | 1234 |
| user  | user |
 
## Chức năng
 
| Tỉ lệ | Chế độ | Mô tả |
|---|---|---|
| Gốc | Stream copy | Cắt nhanh, không re-encode |
| 16:9 | Re-encode + blur | Xuất ngang (YouTube) |
| 9:16 | Re-encode + blur | Xuất dọc (Reels/TikTok) |

======================================================= Lệnh ================================
mkdir video_tool
cd video_tool

mkdir app
mkdir app\core
mkdir app\services
mkdir app\ui
mkdir app\utils
mkdir app\models
mkdir assets

ni app\__init__.py
ni app\main.py
ni app\config.py

ni app\core\__init__.py
ni app\core\auth.py
ni app\core\session.py

ni app\services\__init__.py
ni app\services\ffmpeg_service.py
ni app\services\video_service.py

ni app\ui\__init__.py
ni app\ui\login_view.py
ni app\ui\dashboard_view.py

ni app\utils\__init__.py
ni app\utils\file_picker.py

ni app\models\__init__.py
ni app\models\user.py

ni requirements.txt

python -m venv venv
venv\Scripts\activate

======================================= install lib ======================================
pip install -r requirements.txt

======================================= run =================================
python -m app.main