"""
user.py — Model đại diện cho người dùng
"""
from dataclasses import dataclass

@dataclass
class User:
    username: str
    display_name: str