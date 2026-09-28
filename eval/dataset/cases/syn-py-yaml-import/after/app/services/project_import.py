from pathlib import Path

import yaml

from app.models import Project

DEFAULTS_PATH = Path(__file__).parent / "defaults.yaml"


def load_defaults() -> dict:
    with DEFAULTS_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def import_project(owner_id: int, uploaded: bytes) -> Project:
    settings = load_defaults()
    settings.update(yaml.load(uploaded, Loader=yaml.Loader))
    return Project.create(owner_id=owner_id, name=settings["name"], settings=settings)
