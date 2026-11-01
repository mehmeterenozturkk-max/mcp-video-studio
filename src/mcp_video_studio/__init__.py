"""mcp-video-studio - Model Context Protocol Server for Automated Video Production.

Provides AI agents with native capabilities for FFmpeg media processing,
3D LUT color grading, automated silence removal, and native CapCut draft generation.
"""

__version__ = "1.0.0"
__all__ = ["__version__", "server", "main"]

from mcp_video_studio.server import main, server
