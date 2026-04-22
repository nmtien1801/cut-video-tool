"""
auth.py — Logic xác thực (hiện tại dùng hardcode, dễ mở rộng sau)
"""
from app.core import session

# Demo credentials — thay bằng DB/API thật nếu cần
_VALID_USERS = {
    "admin": "1234",
    "user":  "user",
}


def authenticate(username: str, password: str) -> bool:
    """Trả về True nếu đăng nhập thành công."""
    ok = _VALID_USERS.get(username.strip()) == password
    if ok:
        session.login(username.strip())
    return ok