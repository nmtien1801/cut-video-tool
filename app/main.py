import sys
from PySide6.QtWidgets import QApplication, QMessageBox

from app.ui.login_view import LoginWindow
from app.config import APP_NAME


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    # Kiểm tra ffmpeg trước khi vào app
    try:
        from app.config import FFMPEG_BIN, FFPROBE_BIN  # noqa — trigger validation
    except FileNotFoundError as e:
        QMessageBox.critical(None, "Thiếu FFmpeg", str(e))
        sys.exit(1)

    dashboard_ref = []   # giữ reference để không bị GC

    def show_dashboard():
        from app.ui.dashboard_view import DashboardWindow
        win = DashboardWindow()
        dashboard_ref.append(win)
        win.show()

    login = LoginWindow(on_success=show_dashboard)
    login.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()