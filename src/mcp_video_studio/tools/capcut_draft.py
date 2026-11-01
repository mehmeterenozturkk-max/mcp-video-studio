"""Native CapCut Desktop Draft Generator for mcp-video-studio.

Generates complete, production-ready CapCut Desktop project draft folders
containing valid `draft_content.json` and `draft_meta_info.json` files.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import time
import uuid
from pathlib import Path
from typing import Any

from mcp_video_studio.tools.ffmpeg_ops import extract_audio_and_metadata

logger = logging.getLogger("mcp_video_studio.capcut_draft")


def get_capcut_draft_dir() -> Path:
    """Find the default CapCut Desktop draft directory based on the operating system."""
    system = platform.system()

    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            capcut_path = Path(local_app_data) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
            if capcut_path.exists():
                return capcut_path
            jianying_path = Path(local_app_data) / "JianyingPro Drafts"
            if jianying_path.exists():
                return jianying_path
            return capcut_path
    elif system == "Darwin":  # macOS
        mac_path = Path.home() / "Movies" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
        if mac_path.exists():
            return mac_path
        return mac_path

    # Default fallback for Linux or custom configurations
    return Path.home() / "CapCutDrafts"


def sanitize_filename(name: str) -> str:
    """Sanitize string for safe directory and file naming across OSes."""
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name).strip("_")


def generate_capcut_draft(
    project_name: str,
    clips: list[dict[str, Any]],
    audio_tracks: list[dict[str, Any]] | None = None,
    output_dir: str | None = None,
    width: int = 1080,
    height: int = 1920,
    fps: float = 30.0,
    ratio: str = "9:16",
) -> dict[str, Any]:
    """Generate a fully compliant native CapCut Desktop draft project.

    Args:
        project_name: Name of the project (e.g. 'Viral_Short_01').
        clips: List of video clip definitions.
            Each clip dictionary:
                - 'path' (str, required): Full path to the video file.
                - 'start_sec' (float, optional): Start timestamp in the source file. (default: 0.0)
                - 'end_sec' (float, optional): End timestamp in the source file. (default: full duration)
                - 'duration_sec' (float, optional): Explicit duration (used if end_sec is omitted).
                - 'speed' (float, optional): Playback speed multiplier. (default: 1.0)
                - 'volume' (float, optional): Audio volume multiplier. (default: 1.0)
        audio_tracks: Optional list of background music or sound effect clips.
            Each audio dictionary:
                - 'path' (str, required): Full path to audio file.
                - 'timeline_start_sec' (float, optional): Where on timeline this plays. (default: 0.0)
                - 'start_sec' (float, optional): Start offset in audio file. (default: 0.0)
                - 'duration_sec' (float, optional): Duration to play. (default: full audio duration)
                - 'volume' (float, optional): Audio volume. (default: 1.0)
                - 'name' (str, optional): Label for the audio track.
        output_dir: Base directory where CapCut project folder will be created.
                    If None, auto-detects system CapCut Desktop drafts path.
        width: Canvas width (default: 1080).
        height: Canvas height (default: 1920).
        fps: Project frame rate (default: 30.0).
        ratio: Canvas aspect ratio string ('9:16', '16:9', '1:1', 'original').

    Returns:
        Summary dictionary containing project path, duration, and draft details.
    """
    if not clips:
        raise ValueError("At least one video clip must be provided to create a CapCut draft.")

    safe_name = sanitize_filename(project_name) or "Video_Project"
    base_draft_dir = Path(output_dir).resolve() if output_dir else get_capcut_draft_dir()
    project_folder = base_draft_dir / safe_name
    project_folder.mkdir(parents=True, exist_ok=True)

    draft_id = str(uuid.uuid4()).upper()
    now_us = int(time.time() * 1_000_000)

    # Initialize CapCut schema collections
    material_videos: list[dict[str, Any]] = []
    material_audios: list[dict[str, Any]] = []
    material_speeds: list[dict[str, Any]] = []
    material_canvases: list[dict[str, Any]] = []

    video_segments: list[dict[str, Any]] = []
    audio_segments: list[dict[str, Any]] = []

    current_timeline_us = 0

    # 1. Process Video Clips
    for clip in clips:
        clip_path_str = clip.get("path")
        if not clip_path_str:
            continue

        clip_p = Path(clip_path_str).resolve()
        if not clip_p.exists():
            raise FileNotFoundError(f"Video clip file not found: {clip_path_str}")

        # Fetch metadata to accurately obtain source duration and dimensions
        try:
            meta = extract_audio_and_metadata(str(clip_p), extract_audio=False)["metadata"]
            source_dur_sec = meta["duration_sec"]
            vid_w = meta["video"]["width"] if meta["video"] else width
            vid_h = meta["video"]["height"] if meta["video"] else height
        except Exception as exc:
            logger.warning("Could not probe video file '%s': %s. Using default canvas size.", clip_p, exc)
            source_dur_sec = 60.0
            vid_w = width
            vid_h = height

        source_dur_us = int(source_dur_sec * 1_000_000)

        start_sec = max(0.0, float(clip.get("start_sec", 0.0)))
        end_sec = clip.get("end_sec")
        if end_sec is not None:
            clip_dur_sec = max(0.05, float(end_sec) - start_sec)
        elif clip.get("duration_sec") is not None:
            clip_dur_sec = max(0.05, float(clip["duration_sec"]))
        else:
            clip_dur_sec = max(0.05, source_dur_sec - start_sec)

        speed = max(0.1, min(100.0, float(clip.get("speed", 1.0))))
        volume = max(0.0, min(2.0, float(clip.get("volume", 1.0))))

        src_start_us = int(start_sec * 1_000_000)
        src_dur_us = int(clip_dur_sec * 1_000_000)
        target_dur_us = int(src_dur_us / speed)

        # Ensure we do not exceed source duration bounds
        if src_start_us + src_dur_us > source_dur_us and source_dur_us > 0:
            src_dur_us = max(100_000, source_dur_us - src_start_us)
            target_dur_us = int(src_dur_us / speed)

        # Create Material: Video
        mat_video_id = str(uuid.uuid4()).upper()
        material_videos.append({
            "audio_fade": None,
            "extra_type": "option_default",
            "id": mat_video_id,
            "material_name": clip_p.name,
            "path": str(clip_p).replace("\\", "/"),
            "type": "video",
            "duration": source_dur_us,
            "width": vid_w,
            "height": vid_h,
            "category_id": "",
            "category_name": "local",
            "check_flag": 63,
            "reverse_path": "",
            "create_time": int(time.time()),
        })

        # Create Material: Speed
        mat_speed_id = str(uuid.uuid4()).upper()
        material_speeds.append({
            "curve_speed": None,
            "id": mat_speed_id,
            "mode": 0,
            "speed": float(speed),
            "type": "speed",
        })

        # Create Material: Canvas
        mat_canvas_id = str(uuid.uuid4()).upper()
        material_canvases.append({
            "album_image": "",
            "color": "",
            "id": mat_canvas_id,
            "image": "",
            "image_id": "",
            "image_name": "",
            "source_platform": 0,
            "team_id": "",
            "type": "canvas_color",
        })

        # Create Track Segment
        seg_id = str(uuid.uuid4()).upper()
        video_segments.append({
            "clip": {
                "alpha": 1.0,
                "flip": {"horizontal": False, "vertical": False},
                "rotation": 0.0,
                "scale": {"x": 1.0, "y": 1.0},
                "transform": {"x": 0.0, "y": 0.0},
            },
            "enable_adjust": True,
            "enable_color_curves": True,
            "enable_color_wheels": True,
            "enable_lut": True,
            "enable_smart_color": False,
            "extra_material_refs": [mat_speed_id, mat_canvas_id],
            "id": seg_id,
            "material_id": mat_video_id,
            "render_index": 0,
            "reverse": False,
            "source_timerange": {
                "duration": src_dur_us,
                "start": src_start_us,
            },
            "speed_id": mat_speed_id,
            "target_timerange": {
                "duration": target_dur_us,
                "start": current_timeline_us,
            },
            "template_id": "",
            "track_attribute": 0,
            "track_render_index": 0,
            "visible": True,
            "volume": volume,
        })

        current_timeline_us += target_dur_us

    # 2. Process Audio Tracks
    if audio_tracks:
        for audio in audio_tracks:
            aud_path_str = audio.get("path")
            if not aud_path_str:
                continue

            aud_p = Path(aud_path_str).resolve()
            if not aud_p.exists():
                raise FileNotFoundError(f"Audio file not found: {aud_path_str}")

            try:
                meta = extract_audio_and_metadata(str(aud_p), extract_audio=False)["metadata"]
                aud_source_dur_sec = meta["duration_sec"]
            except Exception as exc:
                logger.warning("Could not probe audio file '%s': %s.", aud_p, exc)
                aud_source_dur_sec = current_timeline_us / 1_000_000

            aud_source_dur_us = int(aud_source_dur_sec * 1_000_000)

            tl_start_sec = max(0.0, float(audio.get("timeline_start_sec", 0.0)))
            aud_start_sec = max(0.0, float(audio.get("start_sec", 0.0)))
            aud_dur_sec = float(audio.get("duration_sec", aud_source_dur_sec - aud_start_sec))
            aud_volume = max(0.0, min(2.0, float(audio.get("volume", 1.0))))

            aud_target_start_us = int(tl_start_sec * 1_000_000)
            aud_src_start_us = int(aud_start_sec * 1_000_000)
            aud_dur_us = int(aud_dur_sec * 1_000_000)

            mat_audio_id = str(uuid.uuid4()).upper()
            material_audios.append({
                "app_id": 0,
                "category_id": "",
                "category_name": "local",
                "check_flag": 1,
                "duration": aud_source_dur_us,
                "id": mat_audio_id,
                "name": audio.get("name") or aud_p.name,
                "path": str(aud_p).replace("\\", "/"),
                "source_platform": 0,
                "type": "extract_music",
            })

            aud_speed_id = str(uuid.uuid4()).upper()
            material_speeds.append({
                "curve_speed": None,
                "id": aud_speed_id,
                "mode": 0,
                "speed": 1.0,
                "type": "speed",
            })

            aud_seg_id = str(uuid.uuid4()).upper()
            audio_segments.append({
                "clip": None,
                "enable_adjust": False,
                "extra_material_refs": [aud_speed_id],
                "id": aud_seg_id,
                "material_id": mat_audio_id,
                "render_index": 0,
                "reverse": False,
                "source_timerange": {
                    "duration": aud_dur_us,
                    "start": aud_src_start_us,
                },
                "speed_id": aud_speed_id,
                "target_timerange": {
                    "duration": aud_dur_us,
                    "start": aud_target_start_us,
                },
                "track_attribute": 0,
                "track_render_index": 0,
                "visible": True,
                "volume": aud_volume,
            })

    # Assemble tracks
    tracks: list[dict[str, Any]] = [
        {
            "attribute": 0,
            "flag": 0,
            "id": str(uuid.uuid4()).upper(),
            "is_default_name": True,
            "name": "",
            "segments": video_segments,
            "type": "video",
        }
    ]

    if audio_segments:
        tracks.append({
            "attribute": 0,
            "flag": 0,
            "id": str(uuid.uuid4()).upper(),
            "is_default_name": True,
            "name": "",
            "segments": audio_segments,
            "type": "audio",
        })

    # Total duration is max of video timeline or audio tracks
    total_duration_us = current_timeline_us
    for aseg in audio_segments:
        end_pt = aseg["target_timerange"]["start"] + aseg["target_timerange"]["duration"]
        if end_pt > total_duration_us:
            total_duration_us = end_pt

    # Construct Complete CapCut `draft_content.json`
    draft_content: dict[str, Any] = {
        "canvas_config": {
            "height": height,
            "ratio": ratio,
            "width": width,
        },
        "color_space": 0,
        "config": {
            "adjust_max_index": 1,
            "attachment_info": [],
            "combination_max_index": 1,
            "export_range": None,
            "extract_audio_last_index": 1,
            "lyrics_recognition_id": "",
            "lyrics_sync": True,
            "lyrics_task_id": "",
            "maintrack_adsorb": True,
            "material_save_mode": 0,
            "original_sound_last_index": 1,
            "record_audio_last_index": 1,
            "sticker_max_index": 1,
            "subtitle_recognition_id": "",
            "subtitle_sync": True,
            "subtitle_task_id": "",
            "system_font_list": [],
            "video_mute": False,
            "zoom_info_params": None,
        },
        "cover": None,
        "create_time": now_us,
        "duration": total_duration_us,
        "extra_info": None,
        "fps": float(fps),
        "free_render_index_mode": "on",
        "group_container": None,
        "id": draft_id,
        "keyframe_graph_list": [],
        "keyframes": {
            "adjusts": [],
            "audios": [],
            "effects": [],
            "filters": [],
            "handwrites": [],
            "stickers": [],
            "texts": [],
            "videos": [],
        },
        "last_modified_platform": {
            "app_id": 3704,
            "app_source": "ea",
            "app_version": "5.0.0",
            "device_id": "",
            "hard_disk_id": "",
            "mac_address": "",
            "os": platform.system().lower(),
            "os_version": platform.release(),
        },
        "materials": {
            "audio_balances": [],
            "audio_effects": [],
            "audio_fades": [],
            "audio_track_indexes": [],
            "audios": material_audios,
            "beats": [],
            "canvases": material_canvases,
            "chromas": [],
            "color_curves": [],
            "drafts": [],
            "effects": [],
            "group_options": [],
            "hsl": [],
            "images": [],
            "log_color_wheels": [],
            "manual_deformations": [],
            "masks": [],
            "material_animations": [],
            "material_colors": [],
            "placeholder_researches": [],
            "placeholders": [],
            "plugin_effects": [],
            "primary_color_wheels": [],
            "realtime_denoises": [],
            "shapes": [],
            "smart_crops": [],
            "sound_channel_mappings": [],
            "speeds": material_speeds,
            "stickers": [],
            "tail_leaders": [],
            "text_templates": [],
            "texts": [],
            "time_marks": [],
            "transitions": [],
            "video_effects": [],
            "video_track_indexes": [],
            "videos": material_videos,
            "vocal_beautifys": [],
            "vocal_separations": [],
        },
        "mutable_config": None,
        "name": safe_name,
        "new_version": "103.0.0",
        "platform": {
            "app_id": 3704,
            "app_source": "ea",
            "app_version": "5.0.0",
            "os": platform.system().lower(),
        },
        "relationships": [],
        "render_index_mode": "on",
        "retouch_cover": None,
        "source": "default",
        "static_cover_image_path": "",
        "tracks": tracks,
        "update_time": now_us,
        "version": 360000,
    }

    # Construct CapCut `draft_meta_info.json`
    draft_meta: dict[str, Any] = {
        "draft_fold_path": str(project_folder).replace("\\", "/"),
        "draft_id": draft_id,
        "draft_is_ai_shorts": False,
        "draft_is_invisible": False,
        "draft_json_file": "draft_content.json",
        "draft_name": safe_name,
        "draft_new_version": "",
        "draft_removable_storage_device": "",
        "draft_root_path": "",
        "draft_segment_extra_info": [],
        "draft_timeline_materials_size": 0,
        "tm_draft_cloud_completed": "",
        "tm_draft_cloud_modified": 0,
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_draft_removed": 0,
        "tm_duration": total_duration_us,
    }

    # Write files to project folder
    content_file = project_folder / "draft_content.json"
    meta_file = project_folder / "draft_meta_info.json"

    with open(content_file, "w", encoding="utf-8") as f:
        json.dump(draft_content, f, indent=2, ensure_ascii=False)

    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(draft_meta, f, indent=2, ensure_ascii=False)

    return {
        "success": True,
        "project_name": safe_name,
        "project_folder": str(project_folder),
        "draft_content_path": str(content_file),
        "draft_meta_path": str(meta_file),
        "video_clips_count": len(video_segments),
        "audio_tracks_count": len(audio_segments),
        "total_duration_sec": round(total_duration_us / 1_000_000, 2),
        "canvas_size": f"{width}x{height}",
        "aspect_ratio": ratio,
        "fps": fps,
        "how_to_open": (
            "Open CapCut Desktop. The project will automatically appear on your home screen "
            f"under 'Recent Drafts' named '{safe_name}'."
        ),
    }
