"""Lightweight JSON state memory for last-used job fields and recent exports."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_DEFAULT_STATE: dict[str, Any] = {
    "last_job": {},
    "recent_jobs": [],
    "ui": {
        "client": "Proper Brands",
        "panel_config": "Standard 1 Panel",
        "panel_count": 1,
        "products": ["walk", "golf_essential"],
        "fabric": "Black (NRF 001)",
        "logo_color": "Pantone White C",
        "project_owner": "PB",
        "print_order": "Peerless",
        "knockout_white": True,
    },
}


class StateMemory:
    """Remembers dashboard defaults and recently generated worksheets."""

    def __init__(self, root: Path, max_jobs: int = 30) -> None:
        self.path = root / "data" / "state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_jobs = max_jobs
        if not self.path.exists():
            self._write(_DEFAULT_STATE)

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return json.loads(json.dumps(_DEFAULT_STATE))
        if not isinstance(data, dict):
            return json.loads(json.dumps(_DEFAULT_STATE))
        return data

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def recall_ui(self) -> dict[str, Any]:
        state = self._read()
        merged = dict(_DEFAULT_STATE["ui"])
        merged.update(state.get("ui") or {})
        return merged

    def remember_ui(self, values: dict[str, Any]) -> None:
        state = self._read()
        ui = dict(state.get("ui") or {})
        ui.update(values)
        state["ui"] = ui
        self._write(state)

    def push_job(self, job: dict[str, Any]) -> None:
        state = self._read()
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **job,
        }
        recent = [entry, *(state.get("recent_jobs") or [])]
        state["recent_jobs"] = recent[: self.max_jobs]
        state["last_job"] = entry
        self._write(state)

    def recent_jobs(self, limit: int = 10) -> list[dict[str, Any]]:
        return list(self._read().get("recent_jobs") or [])[:limit]
