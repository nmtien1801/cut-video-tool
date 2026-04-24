"""
video_service.py  (optimized)
──────────────────────────────
Nghiệp vụ xử lý video:
  1. trim_segments   — cắt nhanh bằng stream copy (không re-encode), song song
  2. export_blur     — xuất blur background, song song + GPU encoder

Tối ưu tốc độ:
  • detect_hw_encoder() → GPU encoder (nvenc/videotoolbox/amf) thay libx264
  • filter_complex tính 1 lần cho cả batch (không tính lại mỗi segment)
  • ThreadPoolExecutor: N segments chạy đồng thời
  • MAX_WORKERS = min(os.cpu_count(), 4) — tránh overload I/O
  • Progress được merge theo weighted average giữa các workers
  • trim_segments dùng stream copy nên giữ song song độc lập
"""
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from app.config import DOWNLOADS_DIR
from app.services.ffmpeg_service import (
    run_ffmpeg,
    get_video_info,
    detect_hw_encoder,
    encoder_preset,
)


# ──────────────────────────────────────────────────────────
# Số worker song song tối đa
# CPU encode: giới hạn 2 để tránh tranh nhau core
# GPU encode: có thể tăng lên 4 vì GPU xử lý độc lập với CPU
# ──────────────────────────────────────────────────────────
_CPU_WORKERS = 2
_GPU_WORKERS = 4


# ──────────────────────────────────────────────────────────
# Kiểu dữ liệu cho 1 đoạn cần xử lý
# ──────────────────────────────────────────────────────────
class Segment:
    def __init__(self, start_time: float, duration: float):
        self.start_time = float(start_time)
        self.duration   = float(duration)


# ──────────────────────────────────────────────────────────
# Progress merger thread-safe
# Gộp % của N worker → 1 callback duy nhất lên UI
# ──────────────────────────────────────────────────────────
class _ProgressMerger:
    def __init__(
        self,
        total: int,
        on_progress: Callable[[int, str], None] | None,
    ):
        self._lock     = threading.Lock()
        self._total    = total
        self._pcts     = [0] * total          # % hiện tại của từng segment
        self._marks    = [""] * total         # timemark mới nhất của từng segment
        self._callback = on_progress

    def update(self, idx: int, pct: int, timemark: str):
        with self._lock:
            self._pcts[idx]  = pct
            self._marks[idx] = timemark
            if self._callback:
                overall = int(sum(self._pcts) / self._total)
                # Lấy timemark của segment đang chạy xa nhất
                best_mark = max(self._marks, key=lambda m: m or "")
                self._callback(min(overall, 99), best_mark)


# ──────────────────────────────────────────────────────────
# 1. CẮT NHANH (stream copy — không re-encode), SONG SONG
# ──────────────────────────────────────────────────────────
def trim_segments(
    input_path: str,
    segments: list[Segment],
    on_progress: Callable[[int, str], None] | None = None,
) -> str:
    """
    Cắt nhiều đoạn song song bằng stream copy.
    Trả về đường dẫn thư mục output.
    """
    output_dir = os.path.join(DOWNLOADS_DIR, "Creatimic_Trims")
    os.makedirs(output_dir, exist_ok=True)

    total   = len(segments)
    merger  = _ProgressMerger(total, on_progress)
    ts_base = int(time.time())

    def _cut_one(idx: int, seg: Segment) -> None:
        out_path = os.path.join(output_dir, f"cut_{ts_base}_{idx}.mp4")
        args = [
            "-y",
            "-ss", f"{seg.start_time:.3f}",
            "-t",  f"{seg.duration:.3f}",
            "-i",  input_path,
            "-c",  "copy",
            "-map", "0:v",
            "-map", "0:a?",
            "-avoid_negative_ts", "make_non_negative",
            "-movflags", "+faststart",
            out_path,
        ]
        run_ffmpeg(
            args,
            segment_duration=seg.duration,
            on_progress=lambda pct, tm: merger.update(idx, pct, tm),
        )

    # stream copy nhẹ → có thể chạy nhiều worker hơn
    max_workers = min(total, _GPU_WORKERS)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_cut_one, i, seg): i for i, seg in enumerate(segments)}
        for fut in as_completed(futures):
            fut.result()   # re-raise nếu có lỗi

    if on_progress:
        on_progress(100, "")
    return output_dir


# ──────────────────────────────────────────────────────────
# 2. XUẤT BLUR (re-encode với filter_complex), SONG SONG + GPU
# ──────────────────────────────────────────────────────────
def export_blur(
    input_path: str,
    aspect_ratio: str,          # "16:9" hoặc "9:16"
    segments: list[Segment],
    on_progress: Callable[[int, str], None] | None = None,
) -> str:
    """
    Xuất video với blur background — song song + GPU encoder tự động.

    Tối ưu:
      • filter_complex tính 1 lần, reuse cho mọi segment
      • GPU encoder (nvenc/videotoolbox/amf) thay libx264 → 5–20× nhanh hơn
      • N segments chạy đồng thời trên ThreadPoolExecutor
      • Nếu không có GPU → fallback libx264 với thread tối ưu
    """
    out_w = 1080 if aspect_ratio == "9:16" else 1920
    out_h = 1920 if aspect_ratio == "9:16" else 1080
    ratio_tag = aspect_ratio.replace(":", "x")

    # ── Probe video 1 lần ──────────────────────────────────
    info      = get_video_info(input_path)
    has_audio = info.get("has_audio", False)

    # ── Phát hiện GPU encoder 1 lần (cached) ───────────────
    encoder = detect_hw_encoder()
    is_gpu  = encoder != "libx264"

    # ── filter_complex: tính 1 lần cho cả batch ────────────
    # Tối ưu tốc độ blur: scale nhỏ nền trước, blur mạnh hơn → nhanh hơn nhiều
    bg_w = out_w // 4
    bg_h = out_h // 4
    filter_complex = (
        f"[0:v]split=2[bg_in][fg_in];"
        f"[bg_in]scale={bg_w}:{bg_h}:force_original_aspect_ratio=increase,"
        f"crop={bg_w}:{bg_h},"
        f"boxblur=10:5,scale={out_w}:{out_h}[bg_blur];"
        f"[fg_in]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fg_scaled];"
        f"[bg_blur][fg_scaled]overlay=(W-w)/2:(H-h)/2[outv]"
    )

    # ── Output dir ─────────────────────────────────────────
    output_dir = os.path.join(
        DOWNLOADS_DIR, f"Creatimic_{ratio_tag}_{int(time.time())}"
    )
    os.makedirs(output_dir, exist_ok=True)

    total  = len(segments)
    merger = _ProgressMerger(total, on_progress)

    def _encode_one(idx: int, seg: Segment) -> None:
        out_path = os.path.join(output_dir, f"segment_{idx + 1}.mp4")

        args = [
            "-y",
            "-ss", f"{seg.start_time:.3f}",
            "-t",  f"{seg.duration:.3f}",
            "-i",  input_path,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
        ]

        if has_audio:
            args += ["-map", "0:a?", "-c:a", "aac", "-b:a", "192k"]

        # Encoder + preset args
        args += ["-c:v", encoder]
        args += encoder_preset(encoder)

        if not is_gpu:
            # libx264: dùng hết core nhưng chia đều giữa các worker
            cpu_count = os.cpu_count() or 4
            threads_per_worker = max(1, cpu_count // _CPU_WORKERS)
            args += ["-threads", str(threads_per_worker)]

        args += [
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            out_path,
        ]

        run_ffmpeg(
            args,
            segment_duration=seg.duration,
            on_progress=lambda pct, tm: merger.update(idx, pct, tm),
        )

    # GPU có thể handle nhiều stream song song hơn CPU
    max_workers = min(total, _GPU_WORKERS if is_gpu else _CPU_WORKERS)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_encode_one, i, seg): i for i, seg in enumerate(segments)}
        errors: list[str] = []
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as exc:
                errors.append(str(exc))

    if errors:
        raise RuntimeError("\n---\n".join(errors))

    if on_progress:
        on_progress(100, "")
    return output_dir