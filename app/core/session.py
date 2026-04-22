"""
session.py — Lưu trạng thái đăng nhập trong bộ nhớ
"""
from app.models.user import User

_current_user: User | None = None


def login(username: str) -> User:
    global _current_user
    _current_user = User(username=username, display_name=username)
    return _current_user


def logout() -> None:
    global _current_user
    _current_user = None


def get_current_user() -> User | None:
    return _current_user


def is_logged_in() -> bool:
    return _current_user is not None