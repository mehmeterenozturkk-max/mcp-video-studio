"""Integration tests for Studio UI FastAPI endpoints."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mcp_video_studio.studio_ui import app
from mcp_video_studio.tools.ffmpeg_ops import get_binary_path, run_command


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="module")
def sample_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    ffmpeg_bin = get_binary_path("ffmpeg")
    out_dir = tmp_path_factory.mktemp("ui_media")
    video_path = out_dir / "sample_ui_test.mp4"

    cmd = [
        ffmpeg_bin,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=duration=2:size=320x240:rate=24",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=800:duration=2",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-c:a",
        "aac",
        str(video_path),
    ]
    run_command(cmd)
    return video_path


def test_serve_index(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert "VIDEO STUDIO" in response.text
    assert "Media Pool" in response.text


def test_system_status(client: TestClient):
    response = client.get("/api/system")
    assert response.status_code == 200
    data = response.json()
    assert data["ffmpeg_available"] is True
    assert "ffmpeg" in data["ffmpeg_version"].lower()
    assert "workspace_dir" in data


def test_probe_media(client: TestClient, sample_video: Path):
    response = client.post("/api/probe", json={"file_path": str(sample_video)})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["metadata"]["video"]["width"] == 320
    assert data["metadata"]["video"]["height"] == 240


def test_upload_video(client: TestClient, sample_video: Path):
    with open(sample_video, "rb") as f:
        response = client.post(
            "/api/upload",
            files={"file": ("uploaded_test.mp4", f.read(), "video/mp4")},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert Path(data["file_path"]).exists()
    assert "/media/raw" in data["media_url"]


def test_process_crop(client: TestClient, sample_video: Path):
    response = client.post(
        "/api/process/crop",
        json={
            "input_path": str(sample_video),
            "mode": "blur_pad",
            "target_width": 360,
            "target_height": 640,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert Path(data["output_path"]).exists()


def test_process_lut(client: TestClient, sample_video: Path, tmp_path: Path):
    lut_file = tmp_path / "ui_test.cube"
    lut_file.write_text(
        "TITLE \"UI_Test\"\nLUT_3D_SIZE 2\n0.0 0.0 0.0\n1.0 0.0 0.0\n0.0 1.0 0.0\n1.0 1.0 0.0\n0.0 0.0 1.0\n1.0 0.0 1.0\n0.0 1.0 1.0\n1.0 1.0 1.0\n",
        encoding="utf-8",
    )
    response = client.post(
        "/api/process/lut",
        json={
            "input_path": str(sample_video),
            "lut_path": str(lut_file),
            "intensity": 0.8,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert Path(data["output_path"]).exists()


def test_process_capcut(client: TestClient, sample_video: Path, tmp_path: Path):
    response = client.post(
        "/api/process/capcut",
        json={
            "project_name": "API_CapCut_Test",
            "clips": [{"path": str(sample_video), "start_sec": 0.0, "duration_sec": 1.0}],
            "output_dir": str(tmp_path),
            "width": 1080,
            "height": 1920,
            "fps": 30.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert Path(data["project_folder"]).exists()


def test_stream_media(client: TestClient, sample_video: Path):
    response = client.get(f"/media/raw?path={sample_video}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert len(response.content) > 0
