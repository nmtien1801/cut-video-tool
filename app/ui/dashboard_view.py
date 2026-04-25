import os
import time

from PySide6.QtCore    import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QScrollArea, QFrame,
    QProgressBar, QMessageBox, QSizePolicy, QSpinBox
)

from app.utils.file_picker   import pick_video
from app.services.ffmpeg_service import get_video_info, detect_hw_encoder
from app.services.video_service  import trim_segments, export_blur, Segment
from app.core   import session
from app.config import APP_NAME


# ══════════════════════════════════════════════════════════
# Worker Thread — warm-up GPU encoder detection
# ══════════════════════════════════════════════════════════
class EncoderProbeWorker(QThread):
    done = Signal(str)   # tên encoder

    def run(self):
        enc = detect_hw_encoder()
        self.done.emit(enc)


# ══════════════════════════════════════════════════════════
# Worker Thread — chạy ffmpeg không block UI
# ══════════════════════════════════════════════════════════
class ExportWorker(QThread):
    progress = Signal(int, float)
    finished = Signal(str)
    error    = Signal(str)

    def __init__(
        self,
        input_path:   str,
        aspect_ratio: str,
        segments:     list[Segment],
    ):
        super().__init__()
        self.input_path   = input_path
        self.aspect_ratio = aspect_ratio
        self.segments     = segments

    def run(self):
        try:
            def _prog(pct: int, eta: float):
                self.progress.emit(pct, eta)

            if self.aspect_ratio == "original":
                out_dir = trim_segments(
                    self.input_path, self.segments, on_progress=_prog
                )
            else:
                out_dir = export_blur(
                    self.input_path, self.aspect_ratio,
                    self.segments, on_progress=_prog
                )

            self.progress.emit(100, 0.0)
            self.finished.emit(out_dir)
        except Exception as exc:
            self.error.emit(str(exc))


# ══════════════════════════════════════════════════════════
# Widget 1 đoạn segment (start + duration)
# ══════════════════════════════════════════════════════════
class SegmentRow(QFrame):
    def __init__(self, index: int, start: int = 0, duration: int = 10):
        super().__init__()
        self.setStyleSheet("""
            QFrame {
                background:#0f172a; border:1px solid #334155; border-radius:10px;
            }
            QLabel  { color:#94a3b8; font-size:10px; border:none; }
            QSpinBox {
                background:#1e293b; border:1px solid #475569;
                border-radius:6px; padding:4px; color:white;
            }
        """)

        row = QHBoxLayout()
        row.setContentsMargins(10, 8, 10, 8)

        label = QLabel(f"Đoạn {index + 1}")
        label.setFixedWidth(50)
        label.setStyleSheet("color:#60a5fa; font-weight:bold; font-size:12px; border:none;")

        start_lbl = QLabel("Bắt đầu (s)")
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 999999)
        self.start_spin.setValue(start)
        self.start_spin.setFixedWidth(90)
        self.start_spin.setStyleSheet("color:#60a5fa;")

        dur_lbl = QLabel("Thời lượng (s)")
        self.dur_spin = QSpinBox()
        self.dur_spin.setRange(1, 999999)
        self.dur_spin.setValue(duration)
        self.dur_spin.setFixedWidth(90)
        self.dur_spin.setStyleSheet("color:#a78bfa;")

        row.addWidget(label)
        row.addWidget(start_lbl)
        row.addWidget(self.start_spin)
        row.addSpacing(12)
        row.addWidget(dur_lbl)
        row.addWidget(self.dur_spin)
        row.addStretch()
        self.setLayout(row)

    def get_segment(self) -> Segment:
        return Segment(self.start_spin.value(), self.dur_spin.value())


# ══════════════════════════════════════════════════════════
# Dashboard chính
# ══════════════════════════════════════════════════════════
class DashboardWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1200, 750)

        self._input_path:         str | None       = None
        self._video_duration:     float            = 0.0
        self._segment_rows:       list[SegmentRow] = []
        self._worker:             ExportWorker | None = None
        self._aspect_ratio:       str              = "original"
        self._encoder_name:       str              = "đang kiểm tra..."
        self._export_start_time: float             = 0.0
        self._wall_timer:         QTimer           = QTimer(self)

        self._apply_styles()
        self._build_ui()
        self._wall_timer.setInterval(1000)
        self._wall_timer.timeout.connect(self._on_wall_tick)

        self._probe_worker = EncoderProbeWorker()
        self._probe_worker.done.connect(self._on_encoder_detected)
        self._probe_worker.start()

    def _apply_styles(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #0f172a;
                color: white;
                font-family: Arial;
                font-size: 13px;
            }
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: #1e293b; width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #475569; border-radius: 4px;
            }
            QProgressBar {
                background: #1e293b; border-radius: 4px; height: 8px;
                text-align: center; color: transparent;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #8b5cf6
                );
                border-radius: 4px;
            }
            QSpinBox { color: white; }
            QLineEdit {
                background:#1e293b; border:1px solid #334155;
                border-radius:8px; padding:6px; color:white;
            }
        """)

    def _build_ui(self):
        root = QVBoxLayout()
        root.setContentsMargins(30, 20, 30, 20)
        root.setSpacing(16)

        root.addLayout(self._make_header())

        body = QHBoxLayout()
        body.setSpacing(24)
        body.addLayout(self._make_left_panel(),  stretch=1)
        body.addLayout(self._make_right_panel(), stretch=1)
        root.addLayout(body)

        self.setLayout(root)

    def _make_header(self) -> QHBoxLayout:
        h = QHBoxLayout()
        title = QLabel("CREATIMIC STUDIO")
        title.setStyleSheet("font-size:26px; font-weight:900; color:#60a5fa;")

        self.encoder_badge = QLabel(f"⚡ {self._encoder_name}")
        self.encoder_badge.setStyleSheet("""
            background: rgba(139,92,246,0.15); color: #a78bfa;
            border: 1px solid rgba(139,92,246,0.4); border-radius: 8px;
            padding: 4px 12px; font-size: 11px;
        """)

        logout_btn = QPushButton("Đăng Xuất")
        logout_btn.setStyleSheet("""
            QPushButton {
                background: rgba(239,68,68,0.15); color:#f87171;
                border:1px solid rgba(239,68,68,0.5); border-radius:8px;
                padding:6px 16px;
            }
            QPushButton:hover { background:#ef4444; color:white; }
        """)
        logout_btn.clicked.connect(self._handle_logout)

        h.addWidget(title)
        h.addStretch()
        h.addWidget(self.encoder_badge)
        h.addSpacing(12)
        h.addWidget(logout_btn)
        return h

    def _on_encoder_detected(self, encoder: str):
        self._encoder_name = encoder
        is_gpu = encoder != "libx264"
        label  = f"⚡ GPU: {encoder}" if is_gpu else "🖥 CPU: libx264"
        color  = "#a78bfa" if is_gpu else "#94a3b8"
        border = "rgba(139,92,246,0.4)" if is_gpu else "#334155"
        bg     = "rgba(139,92,246,0.15)" if is_gpu else "rgba(30,41,59,0.5)"
        self.encoder_badge.setText(label)
        self.encoder_badge.setStyleSheet(f"""
            background: {bg}; color: {color};
            border: 1px solid {border}; border-radius: 8px;
            padding: 4px 12px; font-size: 11px;
        """)

    def _make_left_panel(self) -> QVBoxLayout:
        v = QVBoxLayout()
        v.setSpacing(12)

        self.select_btn = QPushButton("📁  Chọn Video")
        self.select_btn.setMinimumHeight(80)
        self.select_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.select_btn.setStyleSheet("""
            QPushButton {
                border: 2px dashed #334155; border-radius:16px;
                color:#94a3b8; font-size:14px; font-weight:bold;
                background: transparent;
            }
            QPushButton:hover { border-color: #3b82f6; color:#60a5fa; }
        """)
        self.select_btn.clicked.connect(self._handle_select_file)

        self.info_card = QFrame()
        self.info_card.setStyleSheet("""
            QFrame { background:#1e293b; border:1px solid #334155; border-radius:12px; }
            QLabel { border: none; }
        """)
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(16, 12, 16, 12)
        info_layout.setSpacing(6)

        self.file_name_lbl = QLabel("—")
        self.file_name_lbl.setStyleSheet("color:white; font-weight:bold; font-size:12px;")
        self.file_name_lbl.setWordWrap(True)

        self.duration_lbl = QLabel("—")
        self.duration_lbl.setStyleSheet("color:#60a5fa; font-size:11px;")

        info_layout.addWidget(QLabel("File:"))
        info_layout.addWidget(self.file_name_lbl)
        info_layout.addWidget(QLabel("Thời lượng:"))
        info_layout.addWidget(self.duration_lbl)
        self.info_card.setLayout(info_layout)
        self.info_card.hide()

        v.addWidget(self.select_btn)
        v.addWidget(self.info_card)
        v.addLayout(self._make_ratio_selector())
        v.addStretch()
        return v

    def _make_ratio_selector(self) -> QVBoxLayout:
        v = QVBoxLayout()
        v.setSpacing(8)
        lbl = QLabel("Tỉ lệ đầu ra")
        lbl.setStyleSheet("color:#cbd5e1; font-weight:bold;")
        v.addWidget(lbl)

        self._ratio_btns: dict[str, QPushButton] = {}
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        for rid, label in [("original", "🎬  Gốc"), ("16:9", "▬  16:9"), ("9:16", "▮  9:16")]:
            btn = QPushButton(label)
            btn.setProperty("ratio_id", rid)
            btn.clicked.connect(self._on_ratio_clicked)
            btn.setMinimumHeight(52)
            self._ratio_btns[rid] = btn
            btn_row.addWidget(btn)

        v.addLayout(btn_row)
        self.blur_hint = QLabel("✨ Video sẽ được <b style='color:#facc15'>contain</b> lấp bằng <b style='color:#facc15'>blur</b>")
        self.blur_hint.setStyleSheet("font-size:11px; color:#64748b; border:none;")
        self.blur_hint.setTextFormat(Qt.RichText)
        self.blur_hint.hide()
        v.addWidget(self.blur_hint)

        self._select_ratio("original")
        return v

    def _ratio_btn_style(self, active: bool) -> str:
        if active:
            return "QPushButton { border:2px solid #3b82f6; background:rgba(59,130,246,0.1); border-radius:10px; color:#60a5fa; font-weight:bold; padding:8px; font-size:12px; }"
        return "QPushButton { border:2px solid #334155; background:rgba(15,23,42,0.5); border-radius:10px; color:#64748b; padding:8px; font-size:12px; } QPushButton:hover { border-color:#475569; color:#94a3b8; }"

    def _select_ratio(self, ratio_id: str):
        self._aspect_ratio = ratio_id
        for rid, btn in self._ratio_btns.items():
            btn.setStyleSheet(self._ratio_btn_style(rid == ratio_id))
        self.blur_hint.setVisible(ratio_id != "original")

    def _on_ratio_clicked(self):
        btn = self.sender()
        self._select_ratio(btn.property("ratio_id"))

    def _make_right_panel(self) -> QVBoxLayout:
        v = QVBoxLayout()
        v.setSpacing(12)
        v.addLayout(self._make_segment_count_row())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        self._seg_vbox = QVBoxLayout(container)
        self._seg_vbox.setContentsMargins(0, 0, 0, 0)
        self._seg_vbox.setSpacing(8)
        self._seg_vbox.addStretch()

        scroll.setWidget(container)
        v.addWidget(scroll, stretch=1)

        # Đã loại bỏ duration_info label tại đây theo yêu cầu

        self.action_btn = QPushButton("🚀  BẮT ĐẦU XUẤT")
        self.action_btn.setMinimumHeight(52)
        self.action_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #3b82f6, stop:1 #8b5cf6);
                border:none; border-radius:12px; color:white; font-size:15px; font-weight:bold;
            }
            QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #2563eb, stop:1 #7c3aed); }
            QPushButton:disabled { background:#1e293b; color:#475569; }
        """)
        self.action_btn.clicked.connect(self._handle_action)
        v.addWidget(self.action_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.hide()
        v.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.progress_label.setStyleSheet("color:#94a3b8; font-size:12px; padding:2px 0;")
        self.progress_label.hide()
        v.addWidget(self.progress_label)

        return v

    def _make_segment_count_row(self) -> QHBoxLayout:
        h = QHBoxLayout()
        lbl = QLabel("Số đoạn muốn cắt:")
        lbl.setStyleSheet("color:#cbd5e1; border:none;")
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 20)
        self.count_spin.setValue(2)
        self.count_spin.setFixedWidth(70)
        self.count_spin.setAlignment(Qt.AlignCenter)
        self.count_spin.valueChanged.connect(self._regenerate_segments)
        h.addWidget(lbl)
        h.addStretch()
        h.addWidget(self.count_spin)
        return h

    def _regenerate_segments(self):
        while self._seg_vbox.count() > 1:
            item = self._seg_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._segment_rows.clear()

        if self._video_duration <= 0: return

        count = self.count_spin.value()
        seg_dur = int(self._video_duration / count)
        for i in range(count):
            start = i * seg_dur
            dur   = (int(self._video_duration) - i * seg_dur) if i == count - 1 else seg_dur
            row   = SegmentRow(i, start=start, duration=dur)
            self._segment_rows.append(row)
            self._seg_vbox.insertWidget(i, row)

    def _handle_logout(self):
        session.logout()
        from app.ui.login_view import LoginWindow
        def _show_login():
            self._login_win = LoginWindow(on_success=lambda: (self._login_win.close(), DashboardWindow().show()))
            self._login_win.show()
        self.close()
        _show_login()

    def _handle_select_file(self):
        path = pick_video(self)
        if not path: return
        self._input_path = path
        self.select_btn.setText(f"✅  {os.path.basename(path)}")
        info = get_video_info(path)
        self._video_duration = info.get("duration", 0.0)
        self.file_name_lbl.setText(os.path.basename(path))
        self.duration_lbl.setText(self._fmt(self._video_duration))
        self.info_card.show()
        self._regenerate_segments()

    def _handle_action(self):
        if not self._input_path:
            QMessageBox.warning(self, "Chưa chọn video", "Hãy chọn file video trước.")
            return
        segments = [r.get_segment() for r in self._segment_rows]
        if not segments: return

        self._export_start_time = time.time()
        self._set_processing(True)
        self._worker = ExportWorker(self._input_path, self._aspect_ratio, segments)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, pct: int, eta: float):
        # Lần đầu nhận pct > 0: chuyển từ indeterminate → determinate
        if pct > 0 and self.progress_bar.maximum() == 0:
            self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(pct)
        self._last_pct, self._last_eta = pct, eta
        self._refresh_progress_label()

    def _on_wall_tick(self):
        self._refresh_progress_label()

    def _refresh_progress_label(self):
        elapsed = time.time() - self._export_start_time
        pct = getattr(self, "_last_pct", 0)
        eta = getattr(self, "_last_eta", 0.0)

        if pct > 0 and eta > 0:
            eta_text = f"   ·   còn ~{self._fmt(eta)}"
        elif pct > 0:
            # fallback ETA từ wall-clock
            eta_wall = elapsed / pct * (100 - pct)
            eta_text = f"   ·   còn ~{self._fmt(eta_wall)}"
        else:
            eta_text = "   ·   đang khởi động..."

        self.progress_label.setText(
            f"{pct}%   ·   ⏱ đã chạy {self._fmt(elapsed)}{eta_text}"
        )

    def _on_finished(self, out_dir: str):
        elapsed = time.time() - self._export_start_time
        self._set_processing(False)
        # Đảm bảo progress bar về determinate 100% khi xong
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.show()
        self.progress_label.setText(f"✅ Hoàn tất trong {self._fmt(elapsed)}")
        self.progress_label.show()
        QMessageBox.information(
            self, "Hoàn tất!",
            f"Xuất thành công trong {self._fmt(elapsed)}!\nĐã lưu vào:\n{out_dir}"
        )
        import subprocess, sys
        if sys.platform == "win32": os.startfile(out_dir)
        elif sys.platform == "darwin": subprocess.Popen(["open", out_dir])
        else: subprocess.Popen(["xdg-open", out_dir])
        QTimer.singleShot(4000, self.progress_bar.hide)

    def _on_error(self, msg: str):
        self._set_processing(False)
        QMessageBox.critical(self, "Lỗi xử lý video", msg)

    def _set_processing(self, processing: bool):
        self.action_btn.setEnabled(not processing)
        self.select_btn.setEnabled(not processing)
        self.count_spin.setEnabled(not processing)
        for btn in self._ratio_btns.values(): btn.setEnabled(not processing)

        if processing:
            self._last_pct = 0
            self._last_eta = 0.0
            self.action_btn.setText(f"⚙️  ĐANG XỬ LÝ ({self._aspect_ratio.upper()})...")
            # Bắt đầu bằng indeterminate (range 0,0) → animated pulse
            # Sẽ chuyển sang determinate khi _on_progress nhận pct > 0
            self.progress_bar.setRange(0, 0)
            self.progress_bar.show()
            self.progress_label.setText("0%   ·   ⏱ đang khởi động...")
            self.progress_label.show()
            self._wall_timer.start()
        else:
            self._wall_timer.stop()
            self.action_btn.setText("🚀  BẮT ĐẦU XUẤT")
            self.progress_bar.hide()
            QTimer.singleShot(4000, self.progress_label.hide)

    @staticmethod
    def _fmt(seconds: float) -> str:
        s = int(seconds)
        h, r = divmod(s, 3600)
        m, sec = divmod(r, 60)
        return f"{h:02d}:{m:02d}:{sec:02d}"