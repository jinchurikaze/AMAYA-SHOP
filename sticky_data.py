import json
import logging
from pathlib import Path

log = logging.getLogger("amaya.sticky")

FILE_PATH = Path(__file__).parent / "stickyMessages.json"


def load_sticky_data() -> dict:
    if not FILE_PATH.exists():
        FILE_PATH.write_text("{}", encoding="utf-8")
    try:
        raw = FILE_PATH.read_text(encoding="utf-8")
        return json.loads(raw or "{}")
    except Exception as err:
        log.error("Failed to load stickyMessages.json: %s", err)
        return {}


def save_sticky_data(data: dict) -> None:
    try:
        FILE_PATH.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as err:
        log.error("Failed to save stickyMessages.json: %s", err)
