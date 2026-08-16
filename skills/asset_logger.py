"""Persistent asset log for uploaded logos, generated views, and exported worksheets."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AssetLogger:
    """Append-only JSONL log so mockup runs remain auditable."""

    def __init__(self, root: Path) -> None:
        self.path = root / "data" / "asset_log.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def log(self, event: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event,
            "payload": payload or {},
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def recent(self, limit: int = 25, event: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event and item.get("event") != event:
                continue
            rows.append(item)
            if len(rows) >= limit:
                break
        return rows
