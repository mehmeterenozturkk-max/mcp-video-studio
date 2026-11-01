# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-11-01

### Added
- **FastMCP Server**: Standard Model Context Protocol server implementation supporting both `mcp 1.x` and `mcp 2.x` SDKs.
- **Silence Removal (`remove_silence`)**: Automated detection and synchronized video/audio cutting using FFmpeg `silencedetect` and `filter_complex` timeline splicing.
- **Smart Vertical Cropping (`smart_crop_vertical`)**: Instant conversion from landscape 16:9 to vertical 9:16 Shorts/Reels with `blur_pad`, `center_crop`, and `fit_black_bars` modes.
- **3D LUT Color Grading (`apply_lut_grade`)**: Cinema-grade `.cube` and `.3dl` Look-Up Table processing with adjustable blending intensity (0.0 to 1.0).
- **Media Analysis (`extract_audio_and_metadata`)**: Deep `ffprobe` stream metadata inspection and optional pristine audio ripping.
- **Native CapCut Draft Generator (`generate_capcut_draft`)**: Direct generation of `draft_content.json` and `draft_meta_info.json` project folders with microsecond timeline precision.
- **Resources**: `video-studio://system-info` and `video-studio://presets`.
- Comprehensive test suite with synthetic FFmpeg video generation.
- GitHub Actions CI workflow supporting Ubuntu, Windows, and macOS across Python 3.10, 3.11, and 3.12.
