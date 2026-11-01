"""Local Desktop Studio UI backend built with FastAPI.

Provides an NLE-style interface for FFmpeg processing, 3D LUT grading,
silence removal, and CapCut desktop draft generation.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from mcp_video_studio.tools.capcut_draft import (
    generate_capcut_draft,
    get_capcut_draft_dir,
)
from mcp_video_studio.tools.ffmpeg_ops import (
    apply_lut_grade,
    extract_audio_and_metadata,
    get_binary_path,
    get_video_encoder_info,
    remove_silence,
    run_command,
    smart_crop_vertical,
)

logger = logging.getLogger("mcp_video_studio.studio")

# Temp storage for studio uploads and renders
STUDIO_DIR = Path.home() / ".mcp_video_studio" / "workspace"
UPLOADS_DIR = STUDIO_DIR / "uploads"
RENDERS_DIR = STUDIO_DIR / "renders"

for d in (UPLOADS_DIR, RENDERS_DIR):
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Video Studio NLE", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"


# ---------------------------------------------------------
# Request Models
# ---------------------------------------------------------

class ProbeRequest(BaseModel):
    file_path: str


class SilenceRequest(BaseModel):
    input_path: str
    db_threshold: float = -30.0
    min_silence_duration: float = 0.5
    padding: float = 0.1


class CropRequest(BaseModel):
    input_path: str
    mode: str = "blur_pad"
    target_width: int = 1080
    target_height: int = 1920


class LutRequest(BaseModel):
    input_path: str
    lut_path: str
    intensity: float = 1.0


class CapCutRequest(BaseModel):
    project_name: str
    clips: list[dict[str, Any]]
    audio_tracks: list[dict[str, Any]] | None = None
    output_dir: str | None = None
    width: int = 1080
    height: int = 1920
    fps: float = 30.0
    ratio: str = "9:16"


# ---------------------------------------------------------
# Endpoints
# ---------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def serve_index() -> HTMLResponse:
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Studio frontend not found.")
    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))


@app.get("/api/system")
def get_system_status() -> dict[str, Any]:
    ffmpeg_ok = False
    ffmpeg_ver = "Not detected"
    enc_name = "Detecting..."
    try:
        bin_p = get_binary_path("ffmpeg")
        ffmpeg_ok = True
        res = run_command([bin_p, "-version"], timeout=10)
        ffmpeg_ver = res.stdout.splitlines()[0]
        enc_name, _ = get_video_encoder_info()
    except Exception as exc:
        ffmpeg_ver = str(exc)

    return {
        "ffmpeg_available": ffmpeg_ok,
        "ffmpeg_version": ffmpeg_ver,
        "encoder_name": enc_name,
        "capcut_draft_dir": str(get_capcut_draft_dir()),
        "workspace_dir": str(STUDIO_DIR),
    }


@app.post("/api/probe")
def probe_media(req: ProbeRequest) -> dict[str, Any]:
    p = Path(req.file_path).resolve()
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {req.file_path}")

    try:
        res = extract_audio_and_metadata(str(p), extract_audio=False)
        return res
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    safe_name = Path(file.filename).name
    dest_path = UPLOADS_DIR / safe_name

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        meta = extract_audio_and_metadata(str(dest_path), extract_audio=False)
        return {
            "success": True,
            "file_path": str(dest_path),
            "media_url": f"/media/raw?path={str(dest_path)}",
            "metadata": meta["metadata"],
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Uploaded file could not be probed: {exc}")


@app.post("/api/process/silence")
def process_silence(req: SilenceRequest) -> dict[str, Any]:
    input_p = Path(req.input_path).resolve()
    if not input_p.exists():
        raise HTTPException(status_code=404, detail="Input file not found")

    out_name = f"{input_p.stem}_nosilence_{int(time.time())}{input_p.suffix}"
    out_path = RENDERS_DIR / out_name

    t0 = time.time()
    try:
        res = remove_silence(
            input_path=str(input_p),
            output_path=str(out_path),
            db_threshold=req.db_threshold,
            min_silence_duration=req.min_silence_duration,
            padding=req.padding,
        )
        elapsed = round(time.time() - t0, 2)
        res["elapsed_sec"] = elapsed
        res["media_url"] = f"/media/raw?path={str(out_path)}"
        return res
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/process/crop")
def process_crop(req: CropRequest) -> dict[str, Any]:
    input_p = Path(req.input_path).resolve()
    if not input_p.exists():
        raise HTTPException(status_code=404, detail="Input file not found")

    out_name = f"{input_p.stem}_vertical_{req.mode}_{int(time.time())}{input_p.suffix}"
    out_path = RENDERS_DIR / out_name

    t0 = time.time()
    try:
        res = smart_crop_vertical(
            input_path=str(input_p),
            output_path=str(out_path),
            mode=req.mode,
            target_width=req.target_width,
            target_height=req.target_height,
        )
        elapsed = round(time.time() - t0, 2)
        res["elapsed_sec"] = elapsed
        res["media_url"] = f"/media/raw?path={str(out_path)}"
        return res
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/process/lut")
def process_lut(req: LutRequest) -> dict[str, Any]:
    input_p = Path(req.input_path).resolve()
    lut_p = Path(req.lut_path).resolve()

    if not input_p.exists():
        raise HTTPException(status_code=404, detail="Input video not found")
    if not lut_p.exists():
        raise HTTPException(status_code=404, detail=f"LUT file not found: {req.lut_path}")

    out_name = f"{input_p.stem}_lut_{int(time.time())}{input_p.suffix}"
    out_path = RENDERS_DIR / out_name

    t0 = time.time()
    try:
        res = apply_lut_grade(
            input_path=str(input_p),
            lut_path=str(lut_p),
            output_path=str(out_path),
            intensity=req.intensity,
        )
        elapsed = round(time.time() - t0, 2)
        res["elapsed_sec"] = elapsed
        res["media_url"] = f"/media/raw?path={str(out_path)}"
        return res
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/process/capcut")
def process_capcut(req: CapCutRequest) -> dict[str, Any]:
    try:
        res = generate_capcut_draft(
            project_name=req.project_name,
            clips=req.clips,
            audio_tracks=req.audio_tracks,
            output_dir=req.output_dir,
            width=req.width,
            height=req.height,
            fps=req.fps,
            ratio=req.ratio,
        )
        return res
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/media/raw")
def stream_media(path: str) -> FileResponse:
    p = Path(path).resolve()
    if not p.exists():
        raise HTTPException(status_code=404, detail="Media file not found")

    suffix = p.suffix.lower()
    media_types = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
    }
    media_type = media_types.get(suffix, "application/octet-stream")
    return FileResponse(p, media_type=media_type)


def start_server(host: str = "127.0.0.1", port: int = 7860) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    start_server()
