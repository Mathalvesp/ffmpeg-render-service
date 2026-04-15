import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse

app = FastAPI(title="FFmpeg Render Service")


@app.get("/health")
def health():
    return {"ok": True, "service": "ffmpeg-render-service"}


def validate_token(authorization: str | None) -> None:
    expected_token = os.getenv("RENDER_API_TOKEN")

    if not expected_token:
        raise HTTPException(
            status_code=500,
            detail="RENDER_API_TOKEN não configurado no servidor"
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Authorization Bearer token ausente"
        )

    received_token = authorization.replace("Bearer ", "", 1).strip()

    if received_token != expected_token:
        raise HTTPException(
            status_code=403,
            detail="Token inválido"
        )


def save_upload(upload: UploadFile, destination: Path) -> Path:
    file_path = destination / upload.filename
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)
    return file_path


@app.post("/render-upload")
async def render_upload(
    hook: UploadFile = File(...),
    development: UploadFile = File(...),
    cta: UploadFile = File(...),
    authorization: str | None = Header(default=None),
):
    validate_token(authorization)

    temp_dir = Path(tempfile.mkdtemp(prefix="render_"))
    hook_path = save_upload(hook, temp_dir)
    dev_path = save_upload(development, temp_dir)
    cta_path = save_upload(cta, temp_dir)
    output_path = temp_dir / "output.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(hook_path),
        "-i", str(dev_path),
        "-i", str(cta_path),
        "-filter_complex",
        (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v0];"
            "[1:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v1];"
            "[2:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v2];"
            "[0:a]aresample=async=1[a0];"
            "[1:a]aresample=async=1[a1];"
            "[2:a]aresample=async=1[a2];"
            "[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][a]"
        ),
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "FFmpeg falhou",
                "stderr": result.stderr[-4000:],
            },
        )

    return FileResponse(
        path=output_path,
        media_type="video/mp4",
        filename="output.mp4",
    )
