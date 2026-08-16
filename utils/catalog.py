"""Load Weatherman style, fabric, and Pantone catalog from business sources."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "assets" / "catalog" / "catalog.json"


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def product_specs() -> dict[str, dict[str, Any]]:
    return dict(load_catalog()["styles"])


def fabric_rgb_map() -> dict[str, tuple[int, int, int]]:
    out: dict[str, tuple[int, int, int]] = {}
    for name, rec in load_catalog()["fabrics"].items():
        rgb = rec["rgb"]
        out[name] = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
    return out


def fabric_record(name: str) -> dict[str, Any]:
    return dict(load_catalog()["fabrics"].get(name) or {})


def logo_color_names() -> list[str]:
    return [item["name"] for item in load_catalog()["logo_colors"]]


def logo_knockout_mode(name: str) -> str:
    for item in load_catalog()["logo_colors"]:
        if item["name"] == name:
            return str(item.get("knockout") or "none")
    return "none"


def style_labels() -> dict[str, str]:
    labels: dict[str, str] = {}
    for key, spec in product_specs().items():
        cov = spec.get("frame_coverage_in")
        opening = spec.get("opening") or spec.get("subtitle")
        extra = f"{cov}\" · {opening}" if cov else str(opening)
        labels[key] = f"{spec['display_name']} · {extra}"
    return labels


def fabrics_for_styles(keys: list[str], core_only: bool = False) -> list[str]:
    specs = product_specs()
    ordered: list[str] = []
    seen: set[str] = set()
    field = "core_colors" if core_only else "all_colors"
    for key in keys:
        spec = specs.get(key) or {}
        for name in spec.get(field) or spec.get("core_colors") or []:
            if name not in seen:
                seen.add(name)
                ordered.append(name)
    if not ordered:
        ordered = list(fabric_rgb_map())
    return ordered


def fabric_caption(name: str) -> str:
    rec = fabric_record(name)
    bits = [name]
    if rec.get("pantone"):
        bits.append(str(rec["pantone"]))
    if rec.get("nrf") and f"(NRF {rec['nrf']})" not in name:
        bits.append(f"NRF {rec['nrf']}")
    if rec.get("kind") == "pattern":
        bits.append("pattern")
    return " · ".join(bits)


def fabric_sheet_lines(name: str) -> list[str]:
    """Worksheet swatch copy: NRF on line 1, Pantone on line 2 when present."""
    rec = fabric_record(name)
    nrf = rec.get("nrf")
    pantone = rec.get("pantone")
    line1 = name
    if nrf and f"(NRF {nrf})" not in name:
        line1 = f"{name} (NRF {nrf})"
    lines = [line1]
    if pantone:
        lines.append(str(pantone))
    return lines


def logo_color_record(name: str) -> dict[str, Any]:
    for item in load_catalog()["logo_colors"]:
        if item["name"] == name:
            return dict(item)
    return {}


def logo_color_rgb(name: str) -> tuple[int, int, int]:
    rec = logo_color_record(name)
    rgb = rec.get("rgb") or [255, 255, 255]
    return int(rgb[0]), int(rgb[1]), int(rgb[2])
