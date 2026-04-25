"""
ffmpeg_service.py  (optimized)
───────────────────────────────
Tầng thấp nhất: chạy ffmpeg binary bằng subprocess.Popen với args MẢNG.

Tối ưu so với bản cũ:
  1. detect_hw_encoder()  — tự động chọn GPU encoder (nvenc/videotoolbox/amf)
     và cache kết quả, tránh probe mỗi lần xuất.
  2. run_ffmpeg()         — giữ nguyên interface, thêm stdin=DEVNULL tường minh.
  3. get_video_info()     — thêm width/height để video_service tính filter_complex
     1 lần cho cả batch.
"""
import subprocess
import re
import os
import sys
import functools
from typing import Callable

from app.config import FFMPEG_BIN, FFPROBE_BIN


# ──────────────────────────────────────────────────────────
# Timemark helper
# ──────────────────────────────────────────────────────────
def timemark_to_seconds(timemark: str) -> float:
    """'HH:MM:SS.ms' → float seconds"""
    parts = timemark.split(":")
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    return float(timemark or 0)


# ──────────────────────────────────────────────────────────
# Subprocess kwargs helper (ẩn cửa sổ CMD trên Windows)
# ──────────────────────────────────────────────────────────
def _popen_kwargs() -> dict:
    kwargs: dict = {}
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


# ──────────────────────────────────────────────────────────
# GPU / hardware encoder detection  (cache sau lần đầu)
# ──────────────────────────────────────────────────────────
# Thứ tự ưu tiên: NVIDIA → Apple → AMD → CPU fallback
_HW_CANDIDATES = [
    ("h264_nvenc",      ["-f", "lavfi", "-i", "nullsrc=s=64x64:d=1", "-c:v", "h264_nvenc",      "-f", "null", "-"]),
    ("hevc_videotoolbox",["-f","lavfi","-i","nullsrc=s=64x64:d=1","-c:v","hevc_videotoolbox","-f","null","-"]),
    ("h264_videotoolbox",["-f", "lavfi", "-i", "nullsrc=s=64x64:d=1", "-c:v", "h264_videotoolbox", "-f", "null", "-"]),
    ("h264_amf",        ["-f", "lavfi", "-i", "nullsrc=s=64x64:d=1", "-c:v", "h264_amf",        "-f", "null", "-"]),
    ("h264_qsv",        ["-f", "lavfi", "-i", "nullsrc=s=64x64:d=1", "-c:v", "h264_qsv",        "-f", "null", "-"]),
]

@functools.lru_cache(maxsize=1)
def detect_hw_encoder() -> str:
    """
    Thử từng encoder một bằng cách encode 1 giây null video.
    Trả về tên encoder đầu tiên hoạt động, hoặc 'libx264' nếu không có GPU.
    Kết quả được cache — chỉ probe 1 lần duy nhất trong suốt vòng đời process.
    """
    kwargs = _popen_kwargs()
    for name, test_args in _HW_CANDIDATES:
        try:
            result = subprocess.run(
                [FFMPEG_BIN, "-y"] + test_args,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=8,
                **kwargs,
            )
            if result.returncode == 0:
                return name
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            continue
    return "libx264"


def encoder_preset(encoder: str) -> list[str]:
    """
    Trả về args preset/quality phù hợp với từng encoder.
    GPU encoder dùng 'p4' (balanced) hoặc 'fast', CPU dùng 'ultrafast'.
    """
    if encoder == "h264_nvenc":
        # p1=fastest … p7=slowest; rc=vbr; cq tương đương crf
        return ["-preset", "p4", "-rc", "vbr", "-cq", "23", "-b:v", "0"]
    if encoder in ("h264_videotoolbox", "hevc_videotoolbox"):
        # videotoolbox không có preset, dùng quality (0–100, cao = tốt hơn)
        return ["-q:v", "65", "-realtime", "false"]
    if encoder == "h264_amf":
        return ["-quality", "balanced", "-rc", "cqp", "-qp_i", "23", "-qp_p", "23"]
    if encoder == "h264_qsv":
        return ["-preset", "faster", "-q", "23"]
    # libx264 fallback
    return ["-preset", "ultrafast", "-crf", "23"]


# ──────────────────────────────────────────────────────────
# Lấy thông tin video (duration, has_audio, width, height)
# ──────────────────────────────────────────────────────────
def get_video_info(input_path: str) -> dict:
    """
    Trả về dict: { duration: float, has_audio: bool, width: int, height: int }
    Thêm width/height để video_service tính filter_complex 1 lần cho cả batch.
    """
    args = [
        FFPROBE_BIN,
        "-v", "error",
        "-show_entries",
        "format=duration:stream=codec_type,duration,width,height",
        "-of", "default=noprint_wrappers=1",
        input_path,
    ]
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        **_popen_kwargs(),
    )
    output = result.stdout + result.stderr

    duration = 0.0
    has_audio = False
    width = 0
    height = 0

    for line in output.splitlines():
        line = line.strip()
        if line.startswith("duration="):
            try:
                val = float(line.split("=")[1])
                if val > duration:
                    duration = val
            except ValueError:
                pass
        if line == "codec_type=audio":
            has_audio = True
        if line.startswith("width="):
            try:
                width = int(line.split("=")[1])
            except ValueError:
                pass
        if line.startswith("height="):
            try:
                height = int(line.split("=")[1])
            except ValueError:
                pass

    return {
        "duration":  duration,
        "has_audio": has_audio,
        "width":     width,
        "height":    height,
    }


# ──────────────────────────────────────────────────────────
# Runner chính: chạy ffmpeg, parse progress real-time
# ──────────────────────────────────────────────────────────
def run_ffmpeg(
    args: list[str],
    segment_duration: float = 0.0,
    on_progress: Callable[[int, str, float], None] | None = None,
) -> None:
    """
    Chạy ffmpeg với args mảng (shell=False).
    on_progress(percent, timemark, speed_x) được gọi real-time.

    Dùng -progress pipe:2 để ffmpeg emit progress dạng key=value
    mỗi 0.5 giây — đảm bảo % cập nhật đều kể cả lúc mới khởi động.
    """
    # Chèn -progress pipe:2 -stats_period 0.5 vào trước output file
    # (phải đặt trước output, sau tất cả input/filter args)
    progress_args = ["-progress", "pipe:2", "-stats_period", "0.5"]
    # Tách output file (phần tử cuối) để chèn đúng vị trí
    full_args = [FFMPEG_BIN] + args[:-1] + progress_args + [args[-1]]

    proc = subprocess.Popen(
        full_args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        **_popen_kwargs(),
    )

    stderr_lines: list[str] = []
    _last_speed  = 1.0
    _cur_time_us = 0      # out_time_us từ -progress (microseconds)
    _cur_speed   = 1.0

    for raw in proc.stderr:
        line = raw.decode("utf-8", errors="replace").strip()
        stderr_lines.append(line)

        if not on_progress or segment_duration <= 0:
            continue

        # -progress pipe:2 emit key=value, mỗi block kết thúc bằng progress=continue/end
        if "=" in line:
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()

            if key == "out_time_us":
                try:
                    _cur_time_us = int(val)
                except ValueError:
                    pass

            elif key == "speed":
                # format: "3.45x" hoặc "3.45"
                try:
                    _cur_speed = max(float(val.rstrip("x")), 0.01)
                except ValueError:
                    pass

            elif key == "progress":
                # "continue" hoặc "end" — emit 1 lần mỗi stats_period
                elapsed_sec = _cur_time_us / 1_000_000
                pct = min(int(elapsed_sec / segment_duration * 100), 99)
                timemark = _fmt_seconds(elapsed_sec)
                on_progress(pct, timemark, _cur_speed)

        else:
            # Fallback: parse stderr thường (time= / speed=) khi không có -progress
            m_speed = re.search(r"speed=\s*([\d.]+)x?", line)
            if m_speed:
                try:
                    _last_speed = max(float(m_speed.group(1)), 0.01)
                except ValueError:
                    pass

            m_time = re.search(r"time=(\d{2}:\d{2}:\d{2}\.\d+)", line)
            if m_time:
                elapsed = timemark_to_seconds(m_time.group(1))
                pct     = min(int(elapsed / segment_duration * 100), 99)
                on_progress(pct, m_time.group(1), _last_speed)

    proc.wait()

    if proc.returncode != 0:
        stderr_text = "".join(stderr_lines[-30:])
        raise RuntimeError(
            f"FFmpeg lỗi (exit {proc.returncode}):\n{stderr_text}"
        )


def _fmt_seconds(seconds: float) -> str:
    """float seconds → 'HH:MM:SS.xx' cho timemark display."""
    total = int(seconds)
    h, r  = divmod(total, 3600)
    m, s  = divmod(r, 60)
    frac  = int((seconds - total) * 100)
    return f"{h:02d}:{m:02d}:{s:02d}.{frac:02d}"