# Contributing to mcp-video-studio

Thank you for your interest in contributing to **mcp-video-studio**! We welcome contributions from developers, creators, and AI automation enthusiasts.

## Code of Conduct

Please be respectful and constructive in all issues, pull requests, and discussions.

## Development Setup

1. **Prerequisites**:
   - Python 3.10 or higher
   - [FFmpeg](https://ffmpeg.org/download.html) (including `ffprobe`) installed and present in your system PATH
   - [uv](https://github.com/astral-sh/uv) (recommended) or standard `pip`

2. **Clone the repository**:
   ```bash
   git clone https://github.com/mehmeterenozturkk-max/mcp-video-studio.git
   cd mcp-video-studio
   ```

3. **Create a virtual environment and install dependencies**:
   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv pip install -e ".[dev]"
   ```

4. **Run the test suite**:
   ```bash
   pytest -v
   ```

## Pull Request Guidelines

- Ensure all existing and new unit tests pass (`pytest -v`).
- Keep tool signatures and JSON schemas backward-compatible.
- Use meaningful commit messages adhering to Conventional Commits (e.g. `feat:`, `fix:`, `docs:`, `refactor:`).
- Document new tools or parameters in the `README.md`.

## Submitting Issues

If you find a bug or have a feature request:
1. Check the [Issues tracker](https://github.com/mehmeterenozturkk-max/mcp-video-studio/issues) to see if it has already been reported.
2. Open a new issue with steps to reproduce, FFmpeg version, and system OS details.
