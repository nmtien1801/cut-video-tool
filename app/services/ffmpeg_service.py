"""
ffmpeg_service.py
─────────────────
Tầng thấp nhất: chạy ffmpeg binary bằng subprocess.Popen với args MẢNG.

Tại sao dùng mảng thay vì shell=True?
  • Trên Windows, khi filter_complex chứa ký tự [ ] ; = ( )
    nếu dùng shell=True hoặc nối string → CMD.exe escape sai
    → FFmpeg nhận argument bị vỡ → "Invalid argument / exit 4294967274"
  • Dùng Popen(args_list, shell=False) truyền thẳng vào Win32 CreateProcess
    → KHÔNG qua shell → KHÔNG bị escape → KHÔNG lỗi
"""
import subprocess
import re
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
# Lấy thông tin video (duration, has_audio)
# ──────────────────────────────────────────────────────────
def get_video_info(input_path: str) -> dict:
    """
    Trả về dict: { duration: float, has_audio: bool }
    Dùng ffprobe với args mảng.
    """
    args = [
        FFPROBE_BIN,
        "-v", "error",
        "-show_entries", "format=duration:stream=codec_type",
        "-of", "default=noprint_wrappers=1",
        input_path,
    ]
    result = subprocess.run(args, capture_output=True, text=True)
    output = result.stdout + result.stderr

    duration = 0.0
    has_audio = False

    for line in output.splitlines():
        if line.startswith("duration="):
            try:
                duration = float(line.split("=")[1])
            except ValueError:
                pass
        if line.strip() == "codec_type=audio":
            has_audio = True

    return {"duration": duration, "has_audio": has_audio}


# ──────────────────────────────────────────────────────────
# Runner chính: chạy ffmpeg, parse progress real-time
# ──────────────────────────────────────────────────────────
def run_ffmpeg(
    args: list[str],
    segment_duration: float = 0.0,
    on_progress: Callable[[int, str], None] | None = None,
) -> None:
    """
    Chạy ffmpeg với args mảng (shell=False).
    on_progress(percent: int, timemark: str) được gọi real-time.
    Raise RuntimeError nếu ffmpeg trả về exit code != 0.
    """
    # Thêm binary vào đầu
    full_args = [FFMPEG_BIN] + args

    proc = subprocess.Popen(
        full_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,   # ffmpeg log ra stderr
        # shell=False (mặc định) — QUAN TRỌNG trên Windows
    )

    stderr_lines = []

    # ffmpeg ghi progress vào stderr, đọc từng dòng real-time
    for raw in proc.stderr:
        line = raw.decode("utf-8", errors="replace")
        stderr_lines.append(line)

        if on_progress and segment_duration > 0:
            m = re.search(r"time=(\d{2}:\d{2}:\d{2}\.\d+)", line)
            if m:
                elapsed = timemark_to_seconds(m.group(1))
                pct = min(int(elapsed / segment_duration * 100), 99)
                on_progress(pct, m.group(1))

    proc.wait()

    if proc.returncode != 0:
        stderr_text = "".join(stderr_lines[-30:])  # 30 dòng cuối
        raise RuntimeError(
            f"FFmpeg lỗi (exit {proc.returncode}):\n{stderr_text}"
        )