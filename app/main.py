import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

app = FastAPI(title="FFmpeg Render Service")


@app.get("/health")
def health():
    return {"ok": True, "service": "ffmpeg-render-service"}


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
):
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
