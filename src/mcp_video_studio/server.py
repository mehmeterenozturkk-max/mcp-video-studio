"""FastMCP Server for mcp-video-studio.

Exposes native tools and resources for automated FFmpeg media operations,
3D LUT color grading, silence removal, and native CapCut desktop draft creation.
"""

from __future__ import annotations

import json
import logging
import platform
import shutil
import sys
from typing import Any

# Compatibility bridge supporting both modern mcp 2.x (MCPServer) and mcp 1.x (FastMCP)
try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP

from mcp_video_studio.tools.capcut_draft import (
    generate_capcut_draft as _generate_capcut_draft,
    get_capcut_draft_dir,
)
from mcp_video_studio.tools.ffmpeg_ops import (
    apply_lut_grade as _apply_lut_grade,
    extract_audio_and_metadata as _extract_audio_and_metadata,
    get_binary_path,
    remove_silence as _remove_silence,
    run_command,
    smart_crop_vertical as _smart_crop_vertical,
)

logger = logging.getLogger("mcp_video_studio")

# Initialize MCP Server
server = FastMCP(
    name="mcp-video-studio",
    instructions=(
        "mcp-video-studio is an industrial-grade Model Context Protocol server "
        "designed for automated video editing workflows. It provides tools for "
        "A/V synchronized silence removal, 16:9 to 9:16 smart vertical framing, "
        "3D LUT (.cube) cinematic color grading, comprehensive ffprobe media analysis, "
        "and direct generation of native CapCut Desktop drafts."
    ),
)


@server.tool()
def remove_silence(
    input_path: str,
    output_path: str | None = None,
    db_threshold: float = -30.0,
    min_silence_duration: float = 0.5,
    padding: float = 0.1,
) -> str:
    """Cut silent gaps from a video or audio file while keeping video and audio perfectly in sync.

    Args:
        input_path: Full file path to the source video or audio.
        output_path: Optional explicit output path. Defaults to '{name}_no_silence.{ext}'.
        db_threshold: Volume threshold in dB below which sound is considered silence (e.g. -30.0).
        min_silence_duration: Minimum silence length in seconds to trigger a cut (default: 0.5).
        padding: Seconds of voice buffer retained before and after speech to avoid clipping (default: 0.1).

    Returns:
        JSON string containing cut statistics, durations, reduction percentage, and output path.
    """
    try:
        result = _remove_silence(
            input_path=input_path,
            output_path=output_path,
            db_threshold=db_threshold,
            min_silence_duration=min_silence_duration,
            padding=padding,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        logger.error("Error in remove_silence: %s", exc)
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


@server.tool()
def smart_crop_vertical(
    input_path: str,
    output_path: str | None = None,
    mode: str = "blur_pad",
    target_width: int = 1080,
    target_height: int = 1920,
) -> str:
    """Transform horizontal 16:9 video into 9:16 vertical Shorts, Reels, or TikTok format.

    Args:
        input_path: Full file path to the source video.
        output_path: Optional output path. Defaults to '{name}_vertical_{mode}.{ext}'.
        mode: Framing method:
              - 'blur_pad': (Default) Blurred video background with centered sharp original.
              - 'center_crop': Direct 9:16 crop from the center.
              - 'fit_black_bars': Scale to fit with black letterbox padding.
        target_width: Canvas width (default: 1080).
        target_height: Canvas height (default: 1920).

    Returns:
        JSON string with framing details, target resolution, and output file path.
    """
    try:
        result = _smart_crop_vertical(
            input_path=input_path,
            output_path=output_path,
            mode=mode,
            target_width=target_width,
            target_height=target_height,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        logger.error("Error in smart_crop_vertical: %s", exc)
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


@server.tool()
def apply_lut_grade(
    input_path: str,
    lut_path: str,
    output_path: str | None = None,
    intensity: float = 1.0,
) -> str:
    """Apply professional 3D Look-Up Table (.cube or .3dl) color grading to a video.

    Args:
        input_path: Full file path to the input video.
        lut_path: Path to the .cube or .3dl LUT file.
        output_path: Optional output path. Defaults to '{name}_graded.{ext}'.
        intensity: Grading strength multiplier from 0.0 (original) to 1.0 (100% LUT grade).

    Returns:
        JSON string with LUT details, intensity applied, and output file path.
    """
    try:
        result = _apply_lut_grade(
            input_path=input_path,
            lut_path=lut_path,
            output_path=output_path,
            intensity=intensity,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        logger.error("Error in apply_lut_grade: %s", exc)
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


@server.tool()
def extract_audio_and_metadata(
    input_path: str,
    extract_audio: bool = True,
    audio_format: str = "wav",
    output_audio_path: str | None = None,
) -> str:
    """Extract complete media metadata (FPS, resolution, bitrate, codecs) and optionally extract audio.

    Args:
        input_path: Path to the media file.
        extract_audio: Whether to rip the audio track to a standalone file (default: True).
        audio_format: Format for extracted audio ('wav', 'mp3', 'aac', 'flac').
        output_audio_path: Optional destination path for extracted audio.

    Returns:
        JSON string containing comprehensive audio/video stream parameters and audio file path.
    """
    try:
        result = _extract_audio_and_metadata(
            input_path=input_path,
            extract_audio=extract_audio,
            audio_format=audio_format,
            output_audio_path=output_audio_path,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        logger.error("Error in extract_audio_and_metadata: %s", exc)
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


@server.tool()
def generate_capcut_draft(
    project_name: str,
    clips: list[dict[str, Any]],
    audio_tracks: list[dict[str, Any]] | None = None,
    output_dir: str | None = None,
    width: int = 1080,
    height: int = 1920,
    fps: float = 30.0,
    ratio: str = "9:16",
) -> str:
    """Generate native CapCut Desktop draft_content.json and draft_meta_info.json project files.

    Directly importable into CapCut Desktop / Jianying Pro without manual timeline setup.

    Args:
        project_name: Name of the project (e.g. 'TikTok_Highlights_01').
        clips: List of video clip definitions with 'path', optional 'start_sec', 'end_sec', 'speed', 'volume'.
        audio_tracks: Optional list of background music or sound effects with 'path', 'timeline_start_sec', 'volume'.
        output_dir: Base directory where project will be saved. Defaults to CapCut's native drafts directory.
        width: Canvas width (default: 1080).
        height: Canvas height (default: 1920).
        fps: Timeline frame rate (default: 30.0).
        ratio: Aspect ratio ('9:16', '16:9', '1:1', 'original').

    Returns:
        JSON string with project directory, JSON file paths, timeline duration, and opening instructions.
    """
    try:
        result = _generate_capcut_draft(
            project_name=project_name,
            clips=clips,
            audio_tracks=audio_tracks,
            output_dir=output_dir,
            width=width,
            height=height,
            fps=fps,
            ratio=ratio,
        )
        return json.dumps(result, indent=2)
    except Exception as exc:
        logger.error("Error in generate_capcut_draft: %s", exc)
        return json.dumps({"success": False, "error": str(exc)}, indent=2)


@server.resource("video-studio://system-info")
def get_system_info() -> str:
    """Retrieve host environment status, FFmpeg binaries, and CapCut drafts location."""
    ffmpeg_found = False
    ffprobe_found = False
    ffmpeg_ver = "unknown"

    try:
        ffmpeg_bin = get_binary_path("ffmpeg")
        ffmpeg_found = True
        res = run_command([ffmpeg_bin, "-version"])
        first_line = res.stdout.splitlines()[0] if res.stdout else "unknown"
        ffmpeg_ver = first_line
    except Exception:
        pass

    try:
        get_binary_path("ffprobe")
        ffprobe_found = True
    except Exception:
        pass

    info = {
        "mcp_video_studio_version": "1.0.0",
        "python_version": sys.version,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "ffmpeg": {
            "available": ffmpeg_found,
            "version": ffmpeg_ver,
        },
        "ffprobe": {
            "available": ffprobe_found,
        },
        "capcut_default_drafts_dir": str(get_capcut_draft_dir()),
    }
    return json.dumps(info, indent=2)


@server.resource("video-studio://presets")
def get_presets() -> str:
    """Retrieve standard video formatting and silence removal presets."""
    presets = {
        "aspect_ratios": {
            "9:16": {"width": 1080, "height": 1920, "purpose": "TikTok, Instagram Reels, YouTube Shorts"},
            "16:9": {"width": 1920, "height": 1080, "purpose": "Standard YouTube, Web Video, TV"},
            "1:1": {"width": 1080, "height": 1080, "purpose": "Instagram Feed, LinkedIn Square"},
            "4:5": {"width": 1080, "height": 1350, "purpose": "Instagram Portrait Feed"},
        },
        "silence_removal_profiles": {
            "podcast": {"db_threshold": -32.0, "min_silence_duration": 0.6, "padding": 0.12},
            "fast_paced_vlog": {"db_threshold": -28.0, "min_silence_duration": 0.35, "padding": 0.08},
            "screencast_tutorial": {"db_threshold": -30.0, "min_silence_duration": 0.5, "padding": 0.1},
        },
        "lut_support": [".cube", ".3dl"],
    }
    return json.dumps(presets, indent=2)


def main() -> None:
    """Run the MCP Video Studio server."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    logger.info("Starting mcp-video-studio server (stdio transport)...")
    server.run()


if __name__ == "__main__":
    main()
