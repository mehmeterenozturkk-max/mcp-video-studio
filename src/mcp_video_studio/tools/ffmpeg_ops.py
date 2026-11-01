"""FFmpeg operations for video reframing, silence removal, LUT grading, and probe analysis."""

from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("mcp_video_studio.ffmpeg_ops")


def get_binary_path(binary_name: str) -> str:
    """Resolve executable path from PATH or common system directories."""
    path = shutil.which(binary_name)
    if path:
        return path

    # Check common Windows winget / program paths
    if os.name == "nt":
        possible_dirs = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "FFmpeg" / "bin",
            Path("C:\\ffmpeg\\bin"),
        ]
        for base in possible_dirs:
            if base.exists():
                matches = list(base.glob(f"**/{binary_name}.exe"))
                if matches:
                    return str(matches[0])

    raise RuntimeError(
        f"'{binary_name}' was not found in PATH. Please install FFmpeg and ensure it is in your system PATH."
    )


def escape_filter_path(file_path: str | Path) -> str:
    """Escape file path for FFmpeg filtergraph strings (handles Windows colons and backslashes)."""
    normalized = str(file_path).replace("\\", "/")
    # Escape colon (e.g. C:/ -> C\:/)
    escaped = normalized.replace(":", r"\:")
    return escaped


_CACHED_ENCODER_ARGS: list[str] | None = None
_CACHED_ENCODER_NAME: str | None = None


def get_video_encoder_info() -> tuple[str, list[str]]:
    """Auto-detect the fastest available hardware or software video encoder.

    Evaluates NVIDIA NVENC, Intel QSV, and falls back to optimized CPU libx264.
    Enforces '-pix_fmt yuv420p' to guarantee web browser compatibility and prevent
    slow 10-bit software fallbacks on HDR / smartphone inputs.
    """
    global _CACHED_ENCODER_ARGS, _CACHED_ENCODER_NAME
    if _CACHED_ENCODER_ARGS is not None and _CACHED_ENCODER_NAME is not None:
        return _CACHED_ENCODER_NAME, _CACHED_ENCODER_ARGS

    ffmpeg_bin = get_binary_path("ffmpeg")

    # 1. Test NVIDIA NVENC
    try:
        test_cmd = [
            ffmpeg_bin,
            "-f", "lavfi",
            "-i", "color=c=black:s=64x64:d=0.1",
            "-c:v", "h264_nvenc",
            "-pix_fmt", "yuv420p",
            "-f", "null",
            "-",
        ]
        res = subprocess.run(test_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        if res.returncode == 0:
            _CACHED_ENCODER_NAME = "NVIDIA NVENC (Hardware Accelerated)"
            _CACHED_ENCODER_ARGS = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23", "-pix_fmt", "yuv420p"]
            logger.info("Hardware acceleration active: %s", _CACHED_ENCODER_NAME)
            return _CACHED_ENCODER_NAME, _CACHED_ENCODER_ARGS
    except Exception:
        pass

    # 2. Test Intel QSV
    try:
        test_cmd = [
            ffmpeg_bin,
            "-f", "lavfi",
            "-i", "color=c=black:s=64x64:d=0.1",
            "-c:v", "h264_qsv",
            "-pix_fmt", "nv12",
            "-f", "null",
            "-",
        ]
        res = subprocess.run(test_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        if res.returncode == 0:
            _CACHED_ENCODER_NAME = "Intel QSV (Hardware Accelerated)"
            _CACHED_ENCODER_ARGS = ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "23", "-pix_fmt", "nv12"]
            logger.info("Hardware acceleration active: %s", _CACHED_ENCODER_NAME)
            return _CACHED_ENCODER_NAME, _CACHED_ENCODER_ARGS
    except Exception:
        pass

    # 3. Fallback to CPU libx264 with optimized fast preset
    _CACHED_ENCODER_NAME = "CPU libx264 (Software Optimized)"
    _CACHED_ENCODER_ARGS = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p"]
    logger.info("Encoder fallback: %s", _CACHED_ENCODER_NAME)
    return _CACHED_ENCODER_NAME, _CACHED_ENCODER_ARGS


def get_video_encoder_args() -> list[str]:
    """Return command list of the detected optimal video encoder arguments."""
    _, args = get_video_encoder_info()
    return list(args)


def run_command(cmd: list[str], timeout: int | None = 1800) -> subprocess.CompletedProcess[str]:
    """Execute a subprocess command safely with timeout and detailed error messages."""
    logger.debug("Executing command: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"FFmpeg command timed out after {timeout} seconds: {' '.join(cmd)}") from exc
    except Exception as exc:
        raise RuntimeError(f"Failed to execute FFmpeg command: {exc}") from exc

    if result.returncode != 0:
        err_msg = result.stderr.strip() or result.stdout.strip()
        # Truncate overly verbose output for clean error reporting
        if len(err_msg) > 1000:
            err_msg = err_msg[-1000:]
        raise RuntimeError(f"FFmpeg execution failed (code {result.returncode}):\n{err_msg}")

    return result


def extract_audio_and_metadata(
    input_path: str,
    extract_audio: bool = True,
    audio_format: str = "wav",
    output_audio_path: str | None = None,
) -> dict[str, Any]:
    """Inspect media file with ffprobe and optionally extract pristine audio.

    Args:
        input_path: Path to the input video or audio file.
        extract_audio: Whether to extract the audio stream as a standalone file.
        audio_format: Output audio format ('wav', 'mp3', 'aac', 'flac').
        output_audio_path: Optional explicit output path for the extracted audio.

    Returns:
        Dictionary containing comprehensive metadata and extracted audio path.
    """
    input_p = Path(input_path).resolve()
    if not input_p.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    ffprobe_bin = get_binary_path("ffprobe")
    probe_cmd = [
        ffprobe_bin,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(input_p),
    ]

    res = run_command(probe_cmd)
    probe_data = json.loads(res.stdout)

    fmt_info = probe_data.get("format", {})
    streams = probe_data.get("streams", [])

    duration = float(fmt_info.get("duration", 0.0))
    size_bytes = int(fmt_info.get("size", 0))
    format_name = fmt_info.get("format_name", "unknown")
    bit_rate = int(fmt_info.get("bit_rate", 0))

    video_meta: dict[str, Any] | None = None
    audio_meta: dict[str, Any] | None = None

    for s in streams:
        codec_type = s.get("codec_type")
        if codec_type == "video" and video_meta is None:
            # Parse frame rate
            fps_str = s.get("r_frame_rate", "0/0")
            fps = 0.0
            if "/" in fps_str:
                num, den = fps_str.split("/")
                if float(den) > 0:
                    fps = round(float(num) / float(den), 3)

            w = int(s.get("width", 0))
            h = int(s.get("height", 0))
            aspect_ratio = f"{w}:{h}"
            if w > 0 and h > 0:
                gcd_val = math.gcd(w, h)
                aspect_ratio = f"{w // gcd_val}:{h // gcd_val}"

            video_meta = {
                "codec": s.get("codec_name"),
                "width": w,
                "height": h,
                "aspect_ratio": aspect_ratio,
                "fps": fps,
                "pix_fmt": s.get("pix_fmt"),
                "bitrate": int(s.get("bit_rate", 0)) if s.get("bit_rate") else None,
                "nb_frames": int(s.get("nb_frames", 0)) if s.get("nb_frames") else None,
            }
        elif codec_type == "audio" and audio_meta is None:
            audio_meta = {
                "codec": s.get("codec_name"),
                "sample_rate": int(s.get("sample_rate", 0)),
                "channels": int(s.get("channels", 0)),
                "channel_layout": s.get("channel_layout", "stereo"),
                "bitrate": int(s.get("bit_rate", 0)) if s.get("bit_rate") else None,
            }

    metadata = {
        "file_name": input_p.name,
        "file_path": str(input_p),
        "duration_sec": duration,
        "file_size_bytes": size_bytes,
        "file_size_mb": round(size_bytes / (1024 * 1024), 2),
        "format": format_name,
        "overall_bitrate": bit_rate,
        "has_video": video_meta is not None,
        "has_audio": audio_meta is not None,
        "video": video_meta,
        "audio": audio_meta,
    }

    extracted_file: str | None = None
    if extract_audio and audio_meta is not None:
        if not output_audio_path:
            output_audio_path = str(input_p.with_name(f"{input_p.stem}_audio.{audio_format}"))
        out_p = Path(output_audio_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        ffmpeg_bin = get_binary_path("ffmpeg")
        audio_codec = {
            "wav": "pcm_s16le",
            "mp3": "libmp3lame",
            "aac": "aac",
            "flac": "flac",
        }.get(audio_format.lower(), "pcm_s16le")

        extract_cmd = [
            ffmpeg_bin,
            "-y",
            "-i",
            str(input_p),
            "-vn",
            "-c:a",
            audio_codec,
            str(out_p),
        ]
        run_command(extract_cmd)
        extracted_file = str(out_p)

    return {
        "success": True,
        "metadata": metadata,
        "audio_extracted_path": extracted_file,
    }


def parse_silence_intervals(stderr_output: str, total_duration: float) -> list[tuple[float, float]]:
    """Parse silencedetect output from FFmpeg stderr and return [(silence_start, silence_end)]."""
    silence_starts: list[float] = []
    silence_intervals: list[tuple[float, float]] = []

    for line in stderr_output.splitlines():
        start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
        if start_match:
            silence_starts.append(float(start_match.group(1)))

        end_match = re.search(r"silence_end:\s*([0-9.]+)", line)
        if end_match:
            end_val = float(end_match.group(1))
            if silence_starts:
                start_val = silence_starts.pop(0)
                silence_intervals.append((start_val, end_val))

    # If an open silence start remained until end of file
    if silence_starts and total_duration > 0:
        start_val = silence_starts.pop(0)
        silence_intervals.append((start_val, total_duration))

    return silence_intervals


def compute_speech_intervals(
    silences: list[tuple[float, float]],
    total_duration: float,
    padding: float = 0.1,
) -> list[tuple[float, float]]:
    """Invert silence intervals into speech intervals with boundary padding."""
    if not silences:
        return [(0.0, total_duration)] if total_duration > 0 else []

    # Sort silences by start time
    sorted_silences = sorted(silences, key=lambda x: x[0])

    speech: list[tuple[float, float]] = []
    current_pos = 0.0

    for s_start, s_end in sorted_silences:
        seg_end = min(total_duration, s_start + padding)
        seg_start = max(0.0, current_pos)
        if seg_end - seg_start > 0.05:  # Keep segments longer than 50ms
            speech.append((seg_start, seg_end))
        current_pos = max(0.0, s_end - padding)

    if current_pos < total_duration:
        seg_start = current_pos
        seg_end = total_duration
        if seg_end - seg_start > 0.05:
            speech.append((seg_start, seg_end))

    # Merge overlapping speech intervals if padding caused overlaps
    merged: list[tuple[float, float]] = []
    for start, end in speech:
        if not merged:
            merged.append((start, end))
        else:
            prev_start, prev_end = merged[-1]
            if start <= prev_end:
                merged[-1] = (prev_start, max(prev_end, end))
            else:
                merged.append((start, end))

    return merged


def remove_silence(
    input_path: str,
    output_path: str | None = None,
    db_threshold: float = -30.0,
    min_silence_duration: float = 0.5,
    padding: float = 0.1,
) -> dict[str, Any]:
    """Detect and cleanly cut silent portions from video while maintaining perfect A/V sync.

    Args:
        input_path: Path to source video file.
        output_path: Destination path for the processed video.
        db_threshold: Volume threshold in dB below which audio is treated as silence (e.g. -30.0).
        min_silence_duration: Minimum silence length in seconds to trigger a cut (e.g. 0.5).
        padding: Seconds of speech buffer retained before and after cuts to prevent voice clipping.

    Returns:
        Dictionary with processing statistics, timestamps, and output file location.
    """
    input_p = Path(input_path).resolve()
    if not input_p.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if not output_path:
        output_path = str(input_p.with_name(f"{input_p.stem}_no_silence{input_p.suffix}"))
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    # 1. Inspect file metadata
    meta = extract_audio_and_metadata(str(input_p), extract_audio=False)["metadata"]
    total_duration = meta["duration_sec"]
    has_audio = meta["has_audio"]
    has_video = meta["has_video"]

    if not has_audio or total_duration <= 0:
        raise ValueError("Media file does not contain an audio track to analyze silence.")

    ffmpeg_bin = get_binary_path("ffmpeg")

    # 2. Detect silence intervals (use -vn so FFmpeg only reads audio without decoding video frames)
    detect_cmd = [
        ffmpeg_bin,
        "-vn",
        "-i",
        str(input_p),
        "-af",
        f"silencedetect=noise={db_threshold}dB:d={min_silence_duration}",
        "-f",
        "null",
        "-",
    ]
    detect_res = run_command(detect_cmd)
    silences = parse_silence_intervals(detect_res.stderr, total_duration)

    if not silences:
        # No silence detected; copy file directly to destination
        shutil.copy2(str(input_p), str(out_p))
        return {
            "success": True,
            "silence_detected": False,
            "original_duration_sec": total_duration,
            "new_duration_sec": total_duration,
            "silence_removed_sec": 0.0,
            "cuts_made": 0,
            "output_path": str(out_p),
            "message": "No silence exceeding threshold was found; copied original file.",
        }

    # 3. Compute non-silent segments to retain
    speech_segments = compute_speech_intervals(silences, total_duration, padding=padding)
    if not speech_segments:
        speech_segments = [(0.0, total_duration)]

    # 4. Construct FFmpeg filter_complex for synchronized video and audio trim + concat
    filter_parts: list[str] = []
    concat_inputs: list[str] = []

    for i, (seg_start, seg_end) in enumerate(speech_segments):
        start_str = f"{seg_start:.4f}"
        end_str = f"{seg_end:.4f}"

        if has_video:
            filter_parts.append(f"[0:v]trim=start={start_str}:end={end_str},setpts=PTS-STARTPTS[v{i}]")
            concat_inputs.append(f"[v{i}]")

        filter_parts.append(f"[0:a]atrim=start={start_str}:end={end_str},asetpts=PTS-STARTPTS[a{i}]")
        concat_inputs.append(f"[a{i}]")

    num_segs = len(speech_segments)
    v_flag = 1 if has_video else 0
    a_flag = 1
    concat_filter = f"{''.join(concat_inputs)}concat=n={num_segs}:v={v_flag}:a={a_flag}"
    if has_video:
        concat_filter += "[outv][outa]"
    else:
        concat_filter += "[outa]"
    filter_parts.append(concat_filter)

    full_filter = ";".join(filter_parts)

    cut_cmd = [
        ffmpeg_bin,
        "-y",
        "-hwaccel",
        "auto",
        "-i",
        str(input_p),
        "-filter_complex",
        full_filter,
    ]

    if has_video:
        cut_cmd.extend(["-map", "[outv]", "-map", "[outa]"])
        cut_cmd.extend(get_video_encoder_args())
    else:
        cut_cmd.extend(["-map", "[outa]"])

    cut_cmd.extend(["-c:a", "aac", "-b:a", "192k", str(out_p)])
    run_command(cut_cmd, timeout=max(1800, int(total_duration * 10)))

    new_duration = sum(end - start for start, end in speech_segments)
    silence_removed = max(0.0, total_duration - new_duration)

    return {
        "success": True,
        "silence_detected": True,
        "original_duration_sec": round(total_duration, 2),
        "new_duration_sec": round(new_duration, 2),
        "silence_removed_sec": round(silence_removed, 2),
        "reduction_percentage": round((silence_removed / total_duration) * 100, 1),
        "cuts_made": len(silences),
        "retained_segments_count": len(speech_segments),
        "speech_segments": [{"start": round(s, 2), "end": round(e, 2)} for s, e in speech_segments],
        "output_path": str(out_p),
    }


def smart_crop_vertical(
    input_path: str,
    output_path: str | None = None,
    mode: str = "blur_pad",
    target_width: int = 1080,
    target_height: int = 1920,
) -> dict[str, Any]:
    """Convert landscape 16:9 videos to 9:16 vertical Shorts/Reels/TikTok format.

    Modes:
        - 'blur_pad': Background is blurred and scaled to fill 9:16 canvas,
                      with original video centered and sharp in the middle. (Recommended)
        - 'center_crop': Direct center 9:16 crop filling the full canvas.
        - 'fit_black_bars': Preserves entire video framing padded with black letterbox.

    Args:
        input_path: Source video path.
        output_path: Output video path.
        mode: Conversion mode ('blur_pad', 'center_crop', 'fit_black_bars').
        target_width: Target canvas width (default 1080).
        target_height: Target canvas height (default 1920).

    Returns:
        Dictionary with processing results and output file path.
    """
    input_p = Path(input_path).resolve()
    if not input_p.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if not output_path:
        output_path = str(input_p.with_name(f"{input_p.stem}_vertical_{mode}{input_p.suffix}"))
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg_bin = get_binary_path("ffmpeg")
    w = target_width
    h = target_height

    enc_args = get_video_encoder_args()

    if mode == "blur_pad":
        # Background: fill 9:16, crop excess, blur. Foreground: scale to width, overlay centered.
        filter_spec = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},boxblur=25:5[bg];"
            f"[0:v]scale={w}:-2[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[outv]"
        )
        cmd = [
            ffmpeg_bin,
            "-y",
            "-hwaccel",
            "auto",
            "-i",
            str(input_p),
            "-filter_complex",
            filter_spec,
            "-map",
            "[outv]",
            "-map",
            "0:a?",
            *enc_args,
            "-c:a",
            "copy",
            str(out_p),
        ]
    elif mode == "center_crop":
        # Crop 9:16 region out of the center and scale to target dimensions
        filter_spec = (
            f"crop=w=min(iw\\,ih*{w}/{h}):h=min(ih\\,iw*{h}/{w}),scale={w}:{h}"
        )
        cmd = [
            ffmpeg_bin,
            "-y",
            "-hwaccel",
            "auto",
            "-i",
            str(input_p),
            "-vf",
            filter_spec,
            "-map",
            "0:v",
            "-map",
            "0:a?",
            *enc_args,
            "-c:a",
            "copy",
            str(out_p),
        ]
    elif mode == "fit_black_bars":
        # Scale to fit inside 9:16 without distortion and pad with black
        filter_spec = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
        )
        cmd = [
            ffmpeg_bin,
            "-y",
            "-hwaccel",
            "auto",
            "-i",
            str(input_p),
            "-vf",
            filter_spec,
            "-map",
            "0:v",
            "-map",
            "0:a?",
            *enc_args,
            "-c:a",
            "copy",
            str(out_p),
        ]
    else:
        raise ValueError(f"Unknown mode '{mode}'. Choose from: 'blur_pad', 'center_crop', 'fit_black_bars'")

    run_command(cmd)

    return {
        "success": True,
        "mode": mode,
        "target_resolution": f"{w}x{h}",
        "aspect_ratio": "9:16",
        "output_path": str(out_p),
    }


def apply_lut_grade(
    input_path: str,
    lut_path: str,
    output_path: str | None = None,
    intensity: float = 1.0,
) -> dict[str, Any]:
    """Apply a .cube or .3dl 3D Look-Up Table (LUT) color grade to video.

    Args:
        input_path: Path to the input video.
        lut_path: Path to the 3D LUT file (.cube or .3dl).
        output_path: Destination path for color graded video.
        intensity: Blending intensity from 0.0 (original) to 1.0 (100% LUT grade).

    Returns:
        Dictionary with processing result and output file path.
    """
    input_p = Path(input_path).resolve()
    lut_p = Path(lut_path).resolve()

    if not input_p.exists():
        raise FileNotFoundError(f"Input video not found: {input_path}")
    if not lut_p.exists():
        raise FileNotFoundError(f"3D LUT file not found: {lut_path}")

    ext = lut_p.suffix.lower()
    if ext not in [".cube", ".3dl"]:
        raise ValueError(f"Unsupported LUT format '{ext}'. Must be .cube or .3dl")

    if not output_path:
        output_path = str(input_p.with_name(f"{input_p.stem}_graded{input_p.suffix}"))
    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)

    intensity = max(0.0, min(1.0, float(intensity)))
    ffmpeg_bin = get_binary_path("ffmpeg")
    escaped_lut = escape_filter_path(lut_p)

    enc_args = get_video_encoder_args()

    if math.isclose(intensity, 1.0, rel_tol=1e-3):
        # 100% LUT application
        cmd = [
            ffmpeg_bin,
            "-y",
            "-hwaccel",
            "auto",
            "-i",
            str(input_p),
            "-vf",
            f"lut3d=file='{escaped_lut}'",
            "-map",
            "0:v",
            "-map",
            "0:a?",
            *enc_args,
            "-c:a",
            "copy",
            str(out_p),
        ]
    elif math.isclose(intensity, 0.0, rel_tol=1e-3):
        # 0% LUT: Copy original
        shutil.copy2(str(input_p), str(out_p))
        return {
            "success": True,
            "lut_path": str(lut_p),
            "intensity": 0.0,
            "output_path": str(out_p),
            "note": "Intensity set to 0.0; original video copied without changes.",
        }
    else:
        # Blend original with LUT graded version based on opacity
        filter_spec = (
            f"[0:v]split[orig][lutin];"
            f"[lutin]lut3d=file='{escaped_lut}'[graded];"
            f"[orig][graded]blend=all_opacity={intensity:.3f}[outv]"
        )
        cmd = [
            ffmpeg_bin,
            "-y",
            "-hwaccel",
            "auto",
            "-i",
            str(input_p),
            "-filter_complex",
            filter_spec,
            "-map",
            "[outv]",
            "-map",
            "0:a?",
            *enc_args,
            "-c:a",
            "copy",
            str(out_p),
        ]

    run_command(cmd)

    return {
        "success": True,
        "lut_path": str(lut_p),
        "intensity": round(intensity, 2),
        "output_path": str(out_p),
    }
