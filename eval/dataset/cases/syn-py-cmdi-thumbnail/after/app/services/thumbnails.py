import subprocess
from pathlib import Path

UPLOAD_DIR = Path("/var/app/uploads")


def image_size(path: Path) -> str:
    result = subprocess.run(
        ["identify", "-format", "%wx%h", str(path)], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def make_thumbnail(filename: str, width: int = 200) -> Path:
    source = UPLOAD_DIR / filename
    target = UPLOAD_DIR / "thumbs" / filename
    subprocess.run(f"convert {source} -resize {width}x{width} {target}", shell=True, check=True)
    return target
