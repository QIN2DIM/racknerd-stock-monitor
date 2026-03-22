from __future__ import annotations

import json
from pathlib import Path

from racknerd.models import SavedPaths, SnapshotFile


def save_snapshot(snapshot: SnapshotFile, output_dir: Path) -> SavedPaths:
    output_dir.mkdir(parents=True, exist_ok=True)
    history_dir = output_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    payload = snapshot.model_dump(mode="json")
    serialized = json.dumps(payload, indent=2, ensure_ascii=False)

    latest_path = output_dir / "latest.json"
    timestamp = snapshot.updated_at.strftime("%Y%m%d-%H%M%S")
    history_path = history_dir / f"{timestamp}.json"

    latest_path.write_text(serialized + "\n", encoding="utf-8")
    history_path.write_text(serialized + "\n", encoding="utf-8")

    return SavedPaths(latest_path=latest_path, history_path=history_path)
