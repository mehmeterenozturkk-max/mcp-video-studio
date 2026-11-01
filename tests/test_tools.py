"""Unit and integration tests for mcp-video-studio."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from mcp_video_studio.server import server
from mcp_video_studio.tools.capcut_draft import (
    generate_capcut_draft,
    get_capcut_draft_dir,
    sanitize_filename,
)
from mcp_video_studio.tools.ffmpeg_ops import (
    compute_speech_intervals,
    escape_filter_path,
    extract_audio_and_metadata,
    get_binary_path,
    parse_silence_intervals,
    run_command,
    smart_crop_vertical,
)


# ==========================================
# Unit Tests: FFmpeg Logic & Filter Building
# ==========================================


def test_escape_filter_path():
    """Verify Windows drive letter and backslash escaping for FFmpeg filtergraphs."""
    win_path = r"C:\Users\JohnDoe\Luts\cinematic.cube"
    escaped = escape_filter_path(win_path)
    assert r"C\:/Users/JohnDoe/Luts/cinematic.cube" == escaped

    unix_path = "/home/user/luts/vintage.cube"
    escaped_unix = escape_filter_path(unix_path)
    assert "/home/user/luts/vintage.cube" == escaped_unix


def test_parse_silence_intervals():
    """Verify parsing silencedetect FFmpeg output lines."""
    sample_stderr = """
[silencedetect @ 0000021a] silence_start: 2.500
[silencedetect @ 0000021a] silence_end: 4.800 | silence_duration: 2.300
[silencedetect @ 0000021a] silence_start: 8.120
[silencedetect @ 0000021a] silence_end: 9.500 | silence_duration: 1.380
"""
    intervals = parse_silence_intervals(sample_stderr, total_duration=12.0)
    assert len(intervals) == 2
    assert intervals[0] == (2.5, 4.8)
    assert intervals[1] == (8.12, 9.5)


def test_compute_speech_intervals():
    """Verify speech interval calculation from silence intervals with padding."""
    silences = [(2.0, 4.0), (7.0, 9.0)]
    total_duration = 10.0

    speech = compute_speech_intervals(silences, total_duration=total_duration, padding=0.1)
    # Speech should be roughly [0, 2.1], [3.9, 7.1], [8.9, 10.0]
    assert len(speech) == 3
    assert speech[0][0] == 0.0
    assert pytest.approx(speech[0][1], 0.01) == 2.1
    assert pytest.approx(speech[1][0], 0.01) == 3.9
    assert pytest.approx(speech[1][1], 0.01) == 7.1
    assert pytest.approx(speech[2][0], 0.01) == 8.9
    assert speech[2][1] == 10.0


def test_compute_speech_intervals_no_silence():
    """Verify speech interval calculation when no silence is detected."""
    speech = compute_speech_intervals([], total_duration=15.0)
    assert speech == [(0.0, 15.0)]


# ==========================================
# Unit Tests: CapCut Draft Generation
# ==========================================


def test_sanitize_filename():
    """Verify filename sanitization for project names."""
    assert sanitize_filename("My Awesome Video (1080p) #viral!") == "My_Awesome_Video__1080p___viral"
    assert sanitize_filename("podcast_ep_01") == "podcast_ep_01"


def test_generate_capcut_draft_structure(tmp_path: Path):
    """Verify generated draft_content.json and draft_meta_info.json schemas."""
    # Create mock video and audio dummy files
    dummy_video = tmp_path / "clip1.mp4"
    dummy_video.write_bytes(b"mock video data")
    dummy_audio = tmp_path / "bgm.mp3"
    dummy_audio.write_bytes(b"mock audio data")

    project_name = "Test_Project_01"
    clips = [
        {
            "path": str(dummy_video),
            "start_sec": 1.0,
            "duration_sec": 5.0,
            "speed": 1.25,
            "volume": 0.8,
        }
    ]
    audio_tracks = [
        {
            "path": str(dummy_audio),
            "timeline_start_sec": 0.0,
            "duration_sec": 4.0,
            "volume": 0.5,
            "name": "Background Beats",
        }
    ]

    res = generate_capcut_draft(
        project_name=project_name,
        clips=clips,
        audio_tracks=audio_tracks,
        output_dir=str(tmp_path),
        width=1080,
        height=1920,
        fps=30.0,
        ratio="9:16",
    )

    assert res["success"] is True
    assert res["project_name"] == project_name
    assert Path(res["draft_content_path"]).exists()
    assert Path(res["draft_meta_path"]).exists()

    # Inspect draft_content.json
    with open(res["draft_content_path"], encoding="utf-8") as f:
        content = json.load(f)

    assert content["canvas_config"]["width"] == 1080
    assert content["canvas_config"]["height"] == 1920
    assert content["canvas_config"]["ratio"] == "9:16"
    assert content["fps"] == 30.0
    assert content["version"] == 360000

    # Materials validation
    materials = content["materials"]
    assert len(materials["videos"]) == 1
    assert materials["videos"][0]["path"] == str(dummy_video).replace("\\", "/")
    assert len(materials["audios"]) == 1
    assert materials["audios"][0]["path"] == str(dummy_audio).replace("\\", "/")
    assert len(materials["speeds"]) >= 2
    assert len(materials["canvases"]) >= 1

    # Tracks validation
    tracks = content["tracks"]
    assert len(tracks) == 2  # 1 video track + 1 audio track
    v_track = next(t for t in tracks if t["type"] == "video")
    a_track = next(t for t in tracks if t["type"] == "audio")

    assert len(v_track["segments"]) == 1
    v_seg = v_track["segments"][0]
    assert v_seg["source_timerange"]["start"] == 1_000_000  # 1.0s in us
    assert v_seg["source_timerange"]["duration"] == 5_000_000  # 5.0s in us
    assert v_seg["target_timerange"]["duration"] == int(5_000_000 / 1.25)
    assert v_seg["volume"] == 0.8

    assert len(a_track["segments"]) == 1
    a_seg = a_track["segments"][0]
    assert a_seg["target_timerange"]["duration"] == 4_000_000
    assert a_seg["volume"] == 0.5

    # Inspect draft_meta_info.json
    with open(res["draft_meta_path"], encoding="utf-8") as f:
        meta = json.load(f)

    assert meta["draft_name"] == project_name
    assert meta["draft_json_file"] == "draft_content.json"
    assert meta["tm_duration"] > 0


# ==========================================
# Unit Tests: Server Registration
# ==========================================


@pytest.mark.asyncio
async def test_server_tools_registered():
    """Verify that all expected tools and resources are exposed by the FastMCP server."""
    tools = await server.list_tools()
    tool_names = {t.name for t in tools}
    expected_tools = {
        "remove_silence",
        "smart_crop_vertical",
        "apply_lut_grade",
        "extract_audio_and_metadata",
        "generate_capcut_draft",
    }
    assert expected_tools.issubset(tool_names)

    resources = await server.list_resources()
    resource_uris = {str(r.uri) for r in resources}
    expected_resources = {
        "video-studio://system-info",
        "video-studio://presets",
    }
    assert expected_resources.issubset(resource_uris)


# ==========================================
# Integration Tests: Real FFmpeg Execution
# ==========================================


@pytest.fixture(scope="module")
def synthetic_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate a lightweight 2-second synthetic MP4 test video with audio using FFmpeg."""
    ffmpeg_bin = get_binary_path("ffmpeg")
    out_dir = tmp_path_factory.mktemp("media")
    video_path = out_dir / "synthetic_test.mp4"

    cmd = [
        ffmpeg_bin,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=2:size=640x360:rate=30",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=1000:duration=2",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(video_path),
    ]
    run_command(cmd)
    return video_path


def test_real_extract_audio_and_metadata(synthetic_video: Path, tmp_path: Path):
    """Verify real ffprobe metadata extraction and audio extraction."""
    extracted_audio = tmp_path / "extracted.wav"
    res = extract_audio_and_metadata(
        input_path=str(synthetic_video),
        extract_audio=True,
        audio_format="wav",
        output_audio_path=str(extracted_audio),
    )

    assert res["success"] is True
    meta = res["metadata"]
    assert meta["has_video"] is True
    assert meta["has_audio"] is True
    assert meta["video"]["width"] == 640
    assert meta["video"]["height"] == 360
    assert pytest.approx(meta["video"]["fps"], 0.1) == 30.0
    assert extracted_audio.exists()
    assert extracted_audio.stat().st_size > 0


def test_real_smart_crop_vertical(synthetic_video: Path, tmp_path: Path):
    """Verify real FFmpeg execution for 9:16 vertical conversion."""
    out_vertical = tmp_path / "test_vertical.mp4"
    res = smart_crop_vertical(
        input_path=str(synthetic_video),
        output_path=str(out_vertical),
        mode="blur_pad",
        target_width=360,
        target_height=640,
    )

    assert res["success"] is True
    assert out_vertical.exists()
    assert out_vertical.stat().st_size > 0

    # Probe vertical video to confirm dimensions
    probe_res = extract_audio_and_metadata(str(out_vertical), extract_audio=False)
    v_meta = probe_res["metadata"]["video"]
    assert v_meta["width"] == 360
    assert v_meta["height"] == 640


def test_real_apply_lut_grade(synthetic_video: Path, tmp_path: Path):
    """Verify real FFmpeg 3D LUT (.cube) application."""
    from mcp_video_studio.tools.ffmpeg_ops import apply_lut_grade

    lut_file = tmp_path / "test_grade.cube"
    lut_content = """TITLE "Identity"
LUT_3D_SIZE 2
0.0 0.0 0.0
1.0 0.0 0.0
0.0 1.0 0.0
1.0 1.0 0.0
0.0 0.0 1.0
1.0 0.0 1.0
0.0 1.0 1.0
1.0 1.0 1.0
"""
    lut_file.write_text(lut_content, encoding="utf-8")

    graded_output = tmp_path / "test_graded.mp4"
    res = apply_lut_grade(
        input_path=str(synthetic_video),
        lut_path=str(lut_file),
        output_path=str(graded_output),
        intensity=0.8,
    )

    assert res["success"] is True
    assert graded_output.exists()
    assert graded_output.stat().st_size > 0


def test_real_remove_silence(synthetic_video: Path, tmp_path: Path):
    """Verify silence removal pipeline execution."""
    from mcp_video_studio.tools.ffmpeg_ops import remove_silence

    out_cut = tmp_path / "test_cut.mp4"
    res = remove_silence(
        input_path=str(synthetic_video),
        output_path=str(out_cut),
        db_threshold=-30.0,
        min_silence_duration=0.5,
    )

    assert res["success"] is True
    assert out_cut.exists()
    assert out_cut.stat().st_size > 0

