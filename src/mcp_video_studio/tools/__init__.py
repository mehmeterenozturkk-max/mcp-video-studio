"""Tools package for mcp-video-studio."""

from mcp_video_studio.tools.capcut_draft import (
    generate_capcut_draft,
    get_capcut_draft_dir,
)
from mcp_video_studio.tools.ffmpeg_ops import (
    apply_lut_grade,
    extract_audio_and_metadata,
    remove_silence,
    smart_crop_vertical,
)

__all__ = [
    "extract_audio_and_metadata",
    "remove_silence",
    "smart_crop_vertical",
    "apply_lut_grade",
    "generate_capcut_draft",
    "get_capcut_draft_dir",
]
