"""
video_service.py
────────────────
Nghiệp vụ xử lý video:
  1. trim_segments   — cắt nhanh bằng stream copy (không re-encode)
  2. export_blur     — xuất với blur background, đổi tỉ lệ 16:9 / 9:16

Tất cả đều truyền args MẢNG xuống ffmpeg_service.run_ffmpeg
để tránh lỗi "Invalid argument" trên Windows với filter_complex.
"""
import os
import time
from typing import Callable

from app.config import DOWNLOADS_DIR
from app.services.ffmpeg_service import run_ffmpeg, get_video_info


# ──────────────────────────────────────────────────────────
# Kiểu dữ liệu cho 1 đoạn cần xử lý
# ──────────────────────────────────────────────────────────
class Segment:
    def __init__(self, start_time: float, duration: float):
        self.start_time = float(start_time)
        self.duration   = float(duration)


# ──────────────────────────────────────────────────────────
# 1. CẮT NHANH (stream copy — không re-encode)
# ──────────────────────────────────────────────────────────
def trim_segments(
    input_path: str,
    segments: list[Segment],
    on_progress: Callable[[int, str], None] | None = None,
) -> str:
    """
    Cắt nhiều đoạn từ video nguồn bằng stream copy.
    Trả về đường dẫn thư mục output.
    """
    output_dir = os.path.join(DOWNLOADS_DIR, "Creatimic_Trims")
    os.makedirs(output_dir, exist_ok=True)

    total = len(segments)
    for idx, seg in enumerate(segments):
        out_path = os.path.join(output_dir, f"cut_{int(time.time())}_{idx}.mp4")

        args = [
            "-y",
            "-ss", f"{seg.start_time:.3f}",
            "-t",  f"{seg.duration:.3f}",
            "-i",  input_path,
            "-c",  "copy",
            "-map", "0:v",
            "-map", "0:a?",
            "-movflags", "+faststart",
            out_path,
        ]

        def _prog(pct: int, tm: str, _idx=idx, _total=total):
            if on_progress:
                overall = int((_idx + pct / 100) / _total * 100)
                on_progress(min(overall, 99), tm)

        run_ffmpeg(args, segment_duration=seg.duration, on_progress=_prog)

    return output_dir


# ──────────────────────────────────────────────────────────
# 2. XUẤT BLUR (re-encode với filter_complex)
# ──────────────────────────────────────────────────────────
def export_blur(
    input_path: str,
    aspect_ratio: str,          # "16:9" hoặc "9:16"
    segments: list[Segment],
    on_progress: Callable[[int, str], None] | None = None,
) -> str:
    """
    Xuất video với blur background để lấp đầy khung tỉ lệ mục tiêu.
    Trả về đường dẫn thư mục output.

    Thuật toán filter_complex:
      • Split frame gốc thành 2 luồng: bg + fg
      • bg: scale phủ đầy khung → crop → boxblur → làm nền mờ
      • fg: scale vừa khung (giữ tỉ lệ) → pad đen trong suốt để đủ kích thước
      • overlay fg lên trên bg
    """
    out_w = 1080 if aspect_ratio == "9:16" else 1920
    out_h = 1920 if aspect_ratio == "9:16" else 1080
    ratio_tag = aspect_ratio.replace(":", "x")

    output_dir = os.path.join(
        DOWNLOADS_DIR, f"Creatimic_{ratio_tag}_{int(time.time())}"
    )
    os.makedirs(output_dir, exist_ok=True)

    # Kiểm tra audio một lần cho cả batch
    info = get_video_info(input_path)
    has_audio = info.get("has_audio", False)

    # filter_complex — mỗi bước trên 1 dòng cho dễ đọc,
    # nối bằng ";" rồi truyền là 1 phần tử mảng riêng biệt
    filter_complex = (
        f"[0:v]split=2[bg_in][fg_in];"
        f"[bg_in]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
        f"crop={out_w}:{out_h},"
        f"boxblur=20:10[bg_blur];"
        f"[fg_in]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fg_scaled];"
        f"[bg_blur][fg_scaled]overlay=(W-w)/2:(H-h)/2[outv]"
    )

    total = len(segments)
    for idx, seg in enumerate(segments):
        out_path = os.path.join(output_dir, f"segment_{idx + 1}.mp4")

        # ── Xây args MẢNG (mỗi flag + giá trị là phần tử riêng) ──
        # Đây là điểm mấu chốt: KHÔNG nối string, KHÔNG shell=True
        # → Windows nhận đúng argument → KHÔNG lỗi Invalid argument
        args = [
            "-y",
            "-ss", f"{seg.start_time:.3f}",
            "-t",  f"{seg.duration:.3f}",
            "-i",  input_path,
            "-filter_complex", filter_complex,   # 1 phần tử mảng nguyên vẹn
            "-map", "[outv]",
        ]

        if has_audio:
            args += ["-map", "0:a?", "-c:a", "aac", "-b:a", "192k"]

        args += [
            "-c:v",     "libx264",
            "-preset",  "ultrafast",
            "-threads", "0",
            "-crf",     "23",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            out_path,
        ]

        def _prog(pct: int, tm: str, _idx=idx, _total=total):
            if on_progress:
                overall = int((_idx + pct / 100) / _total * 100)
                on_progress(min(overall, 99), tm)

        run_ffmpeg(args, segment_duration=seg.duration, on_progress=_prog)

    return output_dir