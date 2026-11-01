# mcp-video-studio

A Model Context Protocol (MCP) server and local web studio for programmatic FFmpeg video editing and native CapCut Desktop draft generation.

I built this project because automating video edits through Claude and Cursor was frustrating. Large language models understand edit pacing, timestamps, and color grading intent, but turning those decisions into complex FFmpeg filtergraphs or manual timeline cuts in an NLE took too many repetitive steps.

This server exposes atomic, deterministic tools over stdio so AI agents can execute media transformations on disk and export ready-to-open CapCut Desktop projects without intermediate manual timeline reconstruction.

---

## Capabilities

- **Silence Removal (`remove_silence`)**: Identifies silent intervals using `silencedetect`, applies boundary padding buffers to prevent clipped speech onsets/decays, and slices non-silent segments via `trim`/`atrim` + `concat` filters to preserve A/V sync.
- **Vertical 9:16 Reframing (`smart_crop_vertical`)**: Converts horizontal 16:9 footage into vertical Shorts/Reels/TikTok format using ambient background blur padding (`blur_pad`), direct center crop (`center_crop`), or letterboxing (`fit_black_bars`).
- **3D LUT Grading (`apply_lut_grade`)**: Applies `.cube` and `.3dl` Look-Up Tables with Windows-safe path escaping and opacity blending (`blend=all_opacity`).
- **Media Inspection (`extract_audio_and_metadata`)**: Uses `ffprobe` JSON parsing to inspect codecs, resolutions, aspect ratios, framerates, and sample rates, with optional audio stream ripping.
- **CapCut Draft Synthesis (`generate_capcut_draft`)**: Generates valid `draft_content.json` and `draft_meta_info.json` project folders with microsecond precision ($1\text{s} = 1,000,000\,\mu\text{s}$) that CapCut Desktop loads directly.
- **Local NLE Web Studio (`mcp-video-studio-ui`)**: A dark-themed local browser studio (DaVinci/Linear style) for manual inspection, real-time preview, and batch processing.

---

## Installation

### Prerequisites

- Python 3.10 or higher.
- [FFmpeg](https://ffmpeg.org/download.html) and `ffprobe` installed and accessible in your system `PATH`.
  - Windows: `winget install Gyan.FFmpeg`
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt-get install -y ffmpeg`

### Install via pip or uv

```bash
# Direct install
pip install git+https://github.com/mehmeterenozturkk-max/mcp-video-studio.git

# Or with uv
uv pip install git+https://github.com/mehmeterenozturkk-max/mcp-video-studio.git
```

### Local Development Setup

```bash
git clone https://github.com/mehmeterenozturkk-max/mcp-video-studio.git
cd mcp-video-studio
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
```

---

## AI Agent Integration

### Claude Desktop

Add `mcp-video-studio` to your Claude Desktop configuration:

- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "video-studio": {
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

If you installed the package locally in a virtualenv:

```json
{
  "mcpServers": {
    "video-studio": {
      "command": "python",
      "args": [
        "-m",
        "mcp_video_studio.server"
      ]
    }
  }
}
```

### Cursor & Claude Code

In `.cursor/mcp.json` or your MCP client configuration:

```json
{
  "mcpServers": {
    "video-studio": {
      "command": "mcp-video-studio",
      "transport": "stdio"
    }
  }
}
```

---

## Local Desktop Web Studio

For previewing edits outside of chat, run the local desktop studio:

```bash
mcp-video-studio-ui
# Or directly with Python:
python -m mcp_video_studio.studio_ui
```

Navigate to `http://127.0.0.1:7860` to access the interface:
- **Media Pool & Inspector**: Drag-and-drop or path loading with real-time stream metadata inspection.
- **Viewport**: Video playback with timecode (`HH:MM:SS:FF`) and A/B switcher for original vs rendered video.
- **Parameters**: Interactive controls for silence threshold (dB), vertical reframing, 3D LUT blending, and CapCut export.
- **FFmpeg Console**: Live console displaying exact command lines and execution output.

---

## Tool Reference

### `remove_silence`

Cuts dead silence while maintaining audio-video synchronization.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `input_path` | `str` | required | Absolute or relative path to media file. |
| `output_path` | `str` | `None` | Output destination. Defaults to `{stem}_no_silence.{ext}`. |
| `db_threshold` | `float` | `-30.0` | Decibel threshold below which sound is silence. |
| `min_silence_duration` | `float` | `0.5` | Minimum silence length (seconds) to trigger cut. |
| `padding` | `float` | `0.1` | Voice boundary buffer (seconds) before/after speech. |

### `smart_crop_vertical`

Reframes horizontal footage into 9:16 vertical video.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `input_path` | `str` | required | Source video path. |
| `output_path` | `str` | `None` | Output destination. |
| `mode` | `str` | `"blur_pad"` | `"blur_pad"`, `"center_crop"`, or `"fit_black_bars"`. |
| `target_width` | `int` | `1080` | Canvas width. |
| `target_height` | `int` | `1920` | Canvas height. |

### `apply_lut_grade`

Applies a 3D LUT (.cube or .3dl) with opacity blending.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `input_path` | `str` | required | Source video path. |
| `lut_path` | `str` | required | Path to `.cube` or `.3dl` file. |
| `output_path` | `str` | `None` | Output destination. |
| `intensity` | `float` | `1.0` | Blend opacity (0.0 to 1.0). |

### `extract_audio_and_metadata`

Inspects stream properties and optionally extracts audio.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `input_path` | `str` | required | Source media file. |
| `extract_audio` | `bool` | `True` | Extract audio stream. |
| `audio_format` | `str` | `"wav"` | Audio format (`wav`, `mp3`, `aac`, `flac`). |
| `output_audio_path` | `str` | `None` | Destination audio path. |

### `generate_capcut_draft`

Generates an openable CapCut Desktop draft folder.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_name` | `str` | required | Folder and project title. |
| `clips` | `list[dict]` | required | List of clips (`path`, `start_sec`, `end_sec`, `speed`, `volume`). |
| `audio_tracks` | `list[dict]` | `None` | Secondary audio tracks (`path`, `timeline_start_sec`, `volume`). |
| `output_dir` | `str` | `None` | Defaults to system CapCut drafts folder. |
| `width` | `int` | `1080` | Project canvas width. |
| `height` | `int` | `1920` | Project canvas height. |
| `fps` | `float` | `30.0` | Project framerate. |

---

## Technical Notes

### Filtergraph Synchronization
Standard `silenceremove` filters in FFmpeg only strip audio samples, leading to severe A/V desynchronization when applied to video containers. `mcp-video-studio` uses `silencedetect` in a discovery pass to compute valid speech intervals, adds safety padding, and constructs a synchronized `trim`/`atrim` + `concat` filtergraph:

```
[0:v]trim=start=S0:end=E0,setpts=PTS-STARTPTS[v0];
[0:a]atrim=start=S0:end=E0,asetpts=PTS-STARTPTS[a0];
...
[v0][a0][v1][a1]concat=n=N:v=1:a=1[outv][outa]
```

### CapCut Draft Schemas
CapCut Desktop uses microsecond timestamps ($1\text{s} = 1,000,000\,\mu\text{s}$) across its track segments, speeds, and material dictionaries. The draft generator calculates cross-referenced UUID keys for video assets, speeds, and canvas configs so projects appear immediately in the editor's home screen under "Recent Drafts".

---

## Testing

Run tests with pytest:

```bash
pytest -v
```

All video transformations are validated against dynamic synthetic test streams generated via FFmpeg `lavfi` inputs.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
