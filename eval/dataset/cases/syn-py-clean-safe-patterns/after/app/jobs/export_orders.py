import secrets
import subprocess
from pathlib import Path

import yaml

from app.db import get_connection

EXPORT_DIR = Path("/srv/exports").resolve()


def load_job_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def export_path(name: str) -> Path:
    target = (EXPORT_DIR / name).resolve()
    if not target.is_relative_to(EXPORT_DIR):
        raise ValueError("export name escapes the export directory")
    return target


def export_orders(customer_id: int, name: str) -> Path:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, total, created_at FROM orders WHERE customer_id = ? ORDER BY id",
        (customer_id,),
    ).fetchall()
    target = export_path(name)
    with target.open("w", encoding="utf-8") as f:
        f.writelines(f"{row[0]},{row[1]},{row[2]}\n" for row in rows)
    subprocess.run(["gzip", "--force", str(target)], check=True)
    return target.with_suffix(target.suffix + ".gz")


def download_token() -> str:
    return secrets.token_urlsafe(32)
