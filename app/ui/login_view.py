"""
login_view.py — Màn hình đăng nhập (Đã tăng kích thước)
"""
from typing import Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox
)
from PySide6.QtCore import Qt

from app.core.auth import authenticate
from app.config import APP_NAME


class LoginWindow(QWidget):
    def __init__(self, on_success: Callable):
        super().__init__()
        self._on_success = on_success
        self.setWindowTitle(f"{APP_NAME} — Đăng nhập")
        
        # --- TĂNG KÍCH THƯỚC Ở ĐÂY ---
        self.setFixedSize(600, 500) 
        # ----------------------------
        
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("""
            QWidget   { background:#0f172a; color:white; font-family:Arial; }
            QLineEdit {
                background:#1e293b; border:1px solid #334155;
                border-radius:10px; padding:12px; color:white; font-size:14px;
            }
            QLineEdit:focus { border-color:#3b82f6; }
            QPushButton {
                background:#3b82f6; color:white; font-weight:bold;
                border-radius:10px; padding:15px; font-size:15px;
            }
            QPushButton:hover  { background:#2563eb; }
            QPushButton:pressed{ background:#1d4ed8; }
            QLabel { font-size: 13px; color: #94a3b8; }
        """)

        layout = QVBoxLayout()
        # Tăng margin để nội dung không bị dạt ra sát mép khi cửa sổ to
        layout.setContentsMargins(80, 60, 80, 60)
        layout.setSpacing(18)

        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size:32px; font-weight:bold; color:#60a5fa; margin-bottom: 10px;")
        title.setAlignment(Qt.AlignCenter)

        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("Tên đăng nhập")

        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("Mật khẩu")
        self.pass_input.setEchoMode(QLineEdit.Password)
        self.pass_input.returnPressed.connect(self._handle_login)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color:#f87171; font-size:13px;")
        self.error_label.setAlignment(Qt.AlignCenter)

        login_btn = QPushButton("Đăng nhập Hệ thống")
        login_btn.clicked.connect(self._handle_login)

        # Sắp xếp các thành phần
        layout.addStretch()
        layout.addWidget(title)
        layout.addSpacing(20)
        layout.addWidget(QLabel("TÀI KHOẢN"))
        layout.addWidget(self.user_input)
        layout.addWidget(QLabel("MẬT KHẨU"))
        layout.addWidget(self.pass_input)
        layout.addWidget(self.error_label)
        layout.addSpacing(10)
        layout.addWidget(login_btn)
        layout.addStretch()
        
        self.setLayout(layout)

    def _handle_login(self):
        u = self.user_input.text().strip()
        p = self.pass_input.text()
        if not u or not p:
            self.error_label.setText("Vui lòng nhập đầy đủ thông tin.")
            return
        if authenticate(u, p):
            self.close()
            self._on_success()
        else:
            self.error_label.setText("❌ Sai tài khoản hoặc mật khẩu.")
            self.pass_input.clear()