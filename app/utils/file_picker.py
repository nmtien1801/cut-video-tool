"""
file_picker.py — Tiện ích mở hộp thoại chọn file video
"""
from PySide6.QtWidgets import QFileDialog, QWidget


VIDEO_FILTER = "Video Files (*.mp4 *.mov *.avi *.mkv *.webm)"


def pick_video(parent: QWidget | None = None) -> str | None:
    """
    Mở hộp thoại chọn 1 file video.
    Trả về đường dẫn tuyệt đối hoặc None nếu người dùng huỷ.
    """
    path, _ = QFileDialog.getOpenFileName(
        parent, "Chọn video", "", VIDEO_FILTER
    )
    return path if path else None