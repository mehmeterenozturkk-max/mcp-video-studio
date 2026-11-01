<div align="center">

# 🎬 MCP Video Studio

**An industrial-grade Model Context Protocol (MCP) server for automated FFmpeg media pipelines, 3D LUT (.cube) cinematic color grading, A/V synchronized silence removal, and native CapCut Desktop project draft generation.**

[![CI](https://github.com/mehmeterenozturkk-max/mcp-video-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/mehmeterenozturkk-max/mcp-video-studio/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

</div>

---

## 🌟 Overview

**mcp-video-studio** bridges AI agents (Claude Desktop, Cursor, Claude Code, Cline, etc.) with professional video editing backends. Instead of manually slicing podcasts, re-framing 16:9 widescreen footage for TikTok, or manually placing cut markers in timeline editors, your AI agent can process media via FFmpeg and instantly export openable **CapCut Desktop draft projects** with full microsecond precision.

```
+-------------------------------------------------------------------------------+
|                                AI Assistant                                   |
|                (Claude Desktop / Cursor / Claude Code / Cline)                |
+---------------------------------------+---------------------------------------+
                                        | (JSON-RPC over stdio)
                                        v
+-------------------------------------------------------------------------------+
|                       MCP Video Studio Server (FastMCP)                       |
+-------------------+-------------------+-------------------+-------------------+
|   remove_silence  |smart_crop_vertical|  apply_lut_grade  |extract_metadata   |
+-------------------+-------------------+-------------------+-------------------+
                    |                   |                   |
                    v                   v                   v
+-------------------------------------------------------------------------------+
|                                FFmpeg Engine                                  |
|         (silencedetect + filter_complex concat + lut3d + boxblur overlay)     |
+---------------------------------------+---------------------------------------+
                                        |
                                        v
+-------------------------------------------------------------------------------+
|                       Native CapCut Desktop Generator                         |
|                 draft_content.json  +  draft_meta_info.json                   |
|                (Microsecond precision timeline, tracks, speeds)               |
+-------------------------------------------------------------------------------+
```

---

## ⚡ Features

- ✂️ **A/V Synchronized Silence Removal (`remove_silence`)**: Detects dead silence using FFmpeg `silencedetect`, applies intelligent voice padding buffer, and splices non-silent segments with audio-video sync guarantees.
- 📱 **Smart 9:16 Vertical Reframing (`smart_crop_vertical`)**: Automatically converts widescreen (16:9) content to vertical (9:16) format for Shorts, Reels, and TikTok using blurred ambient background padding (`blur_pad`), centered crop (`center_crop`), or black letterbox padding (`fit_black_bars`).
- 🎨 **3D LUT Cinema Color Grading (`apply_lut_grade`)**: Applies industry-standard `.cube` and `.3dl` Look-Up Tables with adjustable blending opacity (0.0 to 1.0) and Windows-safe path escaping.
- 📊 **Deep Media Inspection & Extraction (`extract_audio_and_metadata`)**: Queries resolution, aspect ratios, framerates (FPS), bitrates, codecs, and optionally rips uncompressed WAV or MP3 audio tracks.
- 📐 **Native CapCut Desktop Draft Generator (`generate_capcut_draft`)**: Generates valid `draft_content.json` and `draft_meta_info.json` folders directly readable by CapCut Desktop / Jianying Pro without manual import steps.

---

## 📦 Installation

### Prerequisites

1. **Python 3.10+**
2. **FFmpeg & FFprobe**: Must be installed and available in your system `PATH`.
   - **Windows**: `winget install Gyan.FFmpeg` or `choco install ffmpeg`
   - **macOS**: `brew install ffmpeg`
   - **Linux (Ubuntu/Debian)**: `sudo apt update && sudo apt install -y ffmpeg`

### Quick Install (pip or uv)

```bash
# Direct install with pip
pip install git+https://github.com/mehmeterenozturkk-max/mcp-video-studio.git

# Or with uv
uv pip install git+https://github.com/mehmeterenozturkk-max/mcp-video-studio.git
```

### Local Development Install

```bash
git clone https://github.com/mehmeterenozturkk-max/mcp-video-studio.git
cd mcp-video-studio
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

---

## 🔌 AI Client Integration

### 1. Claude Desktop Configuration

Add `mcp-video-studio` to your Claude Desktop configuration file:

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

#### Option A: Running with `uvx` (Zero-install recommended)

```json
{
  "mcpServers": {
    "mcp-video-studio": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/mehmeterenozturkk-max/mcp-video-studio.git",
        "mcp-video-studio"
      ]
    }
  }
}
```

#### Option B: Running with Python Virtualenv

```json
{
  "mcpServers": {
    "mcp-video-studio": {
      "command": "python",
      "args": [
        "-m",
        "mcp_video_studio.server"
      ],
      "env": {
        "PYTHONPATH": "C:/path/to/mcp-video-studio/src"
      }
    }
  }
}
```

### 2. Cursor IDE / Claude Code Configuration

In `.cursor/mcp.json` or your agent settings:

```json
{
  "mcpServers": {
    "mcp-video-studio": {
      "command": "mcp-video-studio",
      "transport": "stdio"
    }
  }
}
```

---

## 💬 Example Natural Language Prompts

Once configured, simply speak to your AI agent:

> *"Analyze `C:/Media/podcast_ep24.mp4` and extract the audio stream as WAV."*

> *"Remove silence from `interview.mp4` with a -32dB threshold and 0.5s minimum gap, then crop it to 9:16 vertical using blurred background."*

> *"Apply `teal_and_orange.cube` LUT with 80% intensity to `gameplay.mp4` and export it directly to CapCut Desktop drafts as 'Shorts_Vlog_01'."*

> *"Take the first 15 seconds of clip_a.mp4, speed it up by 1.5x, add background_music.mp3 at 50% volume, and create a CapCut draft project ready for editing."*

---

## 🛠️ Tool Specifications

### 1. `remove_silence`
Cuts silence from video or audio files while preserving A/V sync.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `input_path` | `str` | *required* | Source media file path |
| `output_path` | `str` | `None` | Destination path (auto-generated if omitted) |
| `db_threshold` | `float` | `-30.0` | Decibel threshold below which sound is silence |
| `min_silence_duration` | `float` | `0.5` | Minimum silence length (seconds) to trigger a cut |
| `padding` | `float` | `0.1` | Speech buffer (seconds) kept before/after cuts |

### 2. `smart_crop_vertical`
Reframes landscape video into vertical 9:16 aspect ratio.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `input_path` | `str` | *required* | Source video path |
| `output_path` | `str` | `None` | Destination path |
| `mode` | `str` | `"blur_pad"` | `"blur_pad"`, `"center_crop"`, or `"fit_black_bars"` |
| `target_width` | `int` | `1080` | Canvas width |
| `target_height` | `int` | `1920` | Canvas height |

### 3. `apply_lut_grade`
Applies `.cube` or `.3dl` 3D Look-Up Table color grade.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `input_path` | `str` | *required* | Source video path |
| `lut_path` | `str` | *required* | Path to .cube / .3dl LUT file |
| `output_path` | `str` | `None` | Destination path |
| `intensity` | `float` | `1.0` | Opacity blend multiplier (0.0 to 1.0) |

### 4. `extract_audio_and_metadata`
Inspects streams with `ffprobe` and extracts standalone audio.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `input_path` | `str` | *required* | Media file path |
| `extract_audio` | `bool` | `True` | Whether to extract audio file |
| `audio_format` | `str` | `"wav"` | Output format: `"wav"`, `"mp3"`, `"aac"`, `"flac"` |
| `output_audio_path` | `str` | `None` | Output audio destination |

### 5. `generate_capcut_draft`
Generates a native CapCut Desktop draft project folder.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_name` | `str` | *required* | Project title (folder name) |
| `clips` | `list[dict]` | *required* | Video clip list (`path`, `start_sec`, `end_sec`, `speed`, `volume`) |
| `audio_tracks` | `list[dict]` | `None` | Audio tracks (`path`, `timeline_start_sec`, `volume`) |
| `output_dir` | `str` | `None` | Destination directory (auto-detects CapCut drafts folder) |
| `width` | `int` | `1080` | Project canvas width |
| `height` | `int` | `1920` | Project canvas height |
| `fps` | `float` | `30.0` | Frame rate |
| `ratio` | `str` | `"9:16"` | Aspect ratio (`"9:16"`, `"16:9"`, `"1:1"`) |

---

## 🗄️ MCP Resources

- `video-studio://system-info`: Real-time system information including FFmpeg binaries, detected hardware acceleration, and system CapCut drafts path.
- `video-studio://presets`: Curated aspect ratios and silence detection profiles (Podcast, Fast Vlog, Tutorial).

---

## 🧪 Testing

Run the comprehensive unit and integration test suite:

```bash
pytest -v
```

All FFmpeg transformations are tested against dynamic synthetic video streams generated in-memory.

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on submitting pull requests and reporting issues.

---

## 📄 License

This project is open-source software licensed under the [MIT License](LICENSE).
