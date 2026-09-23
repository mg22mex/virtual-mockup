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


def style_family(key: str) -> str:
    spec = product_specs().get(key) or {}
    return str(spec.get("family") or "umbrella")


def style_labels(family: str | None = None) -> dict[str, str]:
    labels: dict[str, str] = {}
    for key, spec in product_specs().items():
        if family and style_family(key) != family:
            continue
        if style_family(key) == "backpack":
            labels[key] = f"{spec['display_name']} · Style #: {spec.get('style_number')}"
            continue
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


def fabric_sheet_label(name: str) -> str:
    """Single-line Fabric Colors label matching Paula sheets (no Pantone sub-line)."""
    return fabric_sheet_lines(name)[0]


def logo_sheet_label(name: str) -> str:
    """Short Logo/Graphic Colors label — Paula sheets use White / Black."""
    token = " ".join(str(name or "").lower().replace("-", " ").split())
    if "white" in token:
        return "White"
    if "black" in token:
        return "Black"
    if "match uploaded" in token:
        return "Match art"
    return str(name or "").strip() or "—"


def logo_color_record(name: str) -> dict[str, Any]:
    for item in load_catalog()["logo_colors"]:
        if item["name"] == name:
            return dict(item)
    return {}


def logo_color_rgb(name: str) -> tuple[int, int, int]:
    rec = logo_color_record(name)
    rgb = rec.get("rgb") or [255, 255, 255]
    return int(rgb[0]), int(rgb[1]), int(rgb[2])


def logo_luminance(rgb: tuple[int, int, int]) -> float:
    return 0.2126 * float(rgb[0]) + 0.7152 * float(rgb[1]) + 0.0722 * float(rgb[2])


def is_light_logo_color(
    name: str | None = None,
    rgb: tuple[int, int, int] | None = None,
) -> bool:
    """True when print color is white / near-white (needs a dark Artwork canvas)."""
    token = " ".join(str(name or "").lower().replace("-", " ").split())
    if any(k in token for k in ("white", "ivory", "cream", "snow", "frost")):
        return True
    if "match uploaded" in token:
        return False
    if rgb is None and name:
        rgb = logo_color_rgb(name)
    if rgb is None:
        return False
    return logo_luminance(rgb) >= 200.0


# Paula tech-pack Artwork preview canvases.
ARTWORK_BG_DARK = (44, 44, 44)  # #2C2C2C — white / light logos
ARTWORK_BG_LIGHT = (245, 245, 245)  # #F5F5F5 — dark logos
ARTWORK_BORDER_DARK = (58, 58, 58)
ARTWORK_BORDER_LIGHT = (226, 232, 240)


def artwork_preview_bg(
    name: str | None = None,
    rgb: tuple[int, int, int] | None = None,
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Return (background_rgb, border_rgb) for the top-right Artwork card."""
    if is_light_logo_color(name, rgb):
        return ARTWORK_BG_DARK, ARTWORK_BORDER_DARK
    return ARTWORK_BG_LIGHT, ARTWORK_BORDER_LIGHT


def backpack_placements(product_key: str = "venture_dry_pack") -> dict[str, dict[str, Any]]:
    """Placement modes for Venture Dry Pack (Style #: 40002) and siblings."""
    spec = product_specs().get(product_key) or {}
    raw = spec.get("placements") or {}
    out: dict[str, dict[str, Any]] = {}
    for key, rec in raw.items():
        out[str(key)] = dict(rec)
    return out


def backpack_placement_labels(product_key: str = "venture_dry_pack") -> dict[str, str]:
    """Map placement key → UI label."""
    return {
        key: str(rec.get("label") or key.replace("_", " ").title())
        for key, rec in backpack_placements(product_key).items()
    }


def resolve_backpack_placement(
    panel_config: str | None,
    product_key: str = "venture_dry_pack",
) -> dict[str, Any]:
    """Resolve a panel_config label/key to placement dims for Style #: 40002."""
    placements = backpack_placements(product_key)
    default_key = str(
        (product_specs().get(product_key) or {}).get("default_placement") or "upper_center"
    )
    token = " ".join(str(panel_config or "").lower().replace("-", " ").split())
    key = default_key
    if token in placements:
        key = token
    else:
        # Exact label match first (avoids "center" matching "Upper center").
        for cand, rec in placements.items():
            label = " ".join(str(rec.get("label") or "").lower().split())
            if token and token == label:
                key = cand
                break
        else:
            if "lower" in token or "right" in token:
                key = "lower_right_center" if "lower_right_center" in placements else key
            elif "upper" in token:
                key = "upper_center" if "upper_center" in placements else key
            elif token == "center" or token == "dead center" or token == "centre":
                key = "center" if "center" in placements else key
    rec = dict(placements.get(key) or placements.get(default_key) or {})
    if not rec:
        rec = {
            "label": "Upper center",
            "width_cm": 13.3,
            "height_cm": 3.7,
        }
    rec["key"] = key if key in placements else default_key
    rec.setdefault("label", key.replace("_", " ").title())
    # Paula sheet callout (may differ from UI label — e.g. Option #4 uses "upper center").
    rec.setdefault(
        "callout",
        str(rec.get("label") or key.replace("_", " ")).lower(),
    )
    rec.setdefault("width_cm", 13.3)
    rec.setdefault("height_cm", 3.7)
    return rec


def backpack_option_label(placement_key: str, fabric_name: str | None) -> str:
    """Return Graphic Sample option tag (e.g. ``#4``) for placement × fabric."""
    placements = backpack_placements()
    rec = placements.get(placement_key) or {}
    by_fabric = rec.get("option_by_fabric") or {}
    fabric = str(fabric_name or "")
    if fabric in by_fabric:
        return str(by_fabric[fabric])
    key = " ".join(fabric.lower().split())
    for name, opt in by_fabric.items():
        nk = " ".join(str(name).lower().split())
        if key and (key == nk or key in nk or nk in key):
            return str(opt)
        if "steel" in key and "steel" in nk:
            return str(opt)
        if "sage" in key and "sage" in nk:
            return str(opt)
        if "black" in key and "black" in nk:
            return str(opt)
    opts = rec.get("options") or []
    return str(opts[0]) if opts else ""
