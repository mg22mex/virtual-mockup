"""Image composition and centimetre-accurate panel mapping for Weatherman mockups.

Coordinate source of truth: assets/catalog/catalog.json
Artwork bound (worksheet standard): 21.6 cm wide × 10 cm tall.
"""

from __future__ import annotations

import math
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont
from PIL.Image import composite as image_composite

from .catalog import fabric_rgb_map, product_specs

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "assets" / "templates"
BACKPACK_DIR = TEMPLATE_DIR / "official" / "backpack"
BACKPACK_PHOTO_MASK = BACKPACK_DIR / "backpack_mask.png"
BACKPACK_LINEART_MASK = BACKPACK_DIR / "backpack_lineart_mask.png"

NAVY = (38, 45, 101)
HEADER_BG = (246, 245, 243)
WHITE = (255, 255, 255)
PANTONE_WHITE_C = (255, 255, 255)
PANTONE_BLACK_C = (45, 41, 38)

FABRIC_COLORS: dict[str, tuple[int, int, int]] = fabric_rgb_map()
PRODUCT_CATALOG: dict[str, dict[str, Any]] = product_specs()

_FONT_CANDIDATES = (
    ROOT / "assets" / "fonts",
    Path("/usr/share/fonts/truetype/liberation"),
    Path("/usr/share/fonts/liberation"),
    Path("/usr/share/fonts/truetype/liberation2"),
)
_FONT_DIR = next((p for p in _FONT_CANDIDATES if (p / "LiberationSans-Regular.ttf").exists()), _FONT_CANDIDATES[0])


def _font(kind: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = {
        "sans": "LiberationSans-Regular.ttf",
        "sans-bold": "LiberationSans-Bold.ttf",
        "serif": "LiberationSerif-Regular.ttf",
        "serif-bold": "LiberationSerif-Bold.ttf",
    }
    path = _FONT_DIR / names.get(kind, names["sans"])
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def shade_color(rgb: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return tuple(int(max(0, min(255, c * factor))) for c in rgb)  # type: ignore[return-value]


def _alpha_over(bg: np.ndarray, fg: np.ndarray) -> np.ndarray:
    bg_f = bg.astype(np.float32) / 255.0
    fg_f = fg.astype(np.float32) / 255.0
    a = fg_f[:, :, 3:4]
    out_rgb = fg_f[:, :, :3] * a + bg_f[:, :, :3] * (1.0 - a)
    out_a = a + bg_f[:, :, 3:4] * (1.0 - a)
    out = np.concatenate([out_rgb, out_a], axis=2)
    return np.clip(out * 255.0, 0, 255).astype(np.uint8)


def warp_to_quad(overlay: Image.Image, canvas_size: tuple[int, int], quad) -> Image.Image:
    """Project an image onto a destination quadrilateral (TL, TR, BR, BL)."""
    ov = np.array(overlay.convert("RGBA"))
    src_h, src_w = ov.shape[:2]
    src = np.float32([[0, 0], [src_w, 0], [src_w, src_h], [0, src_h]])
    dst = np.float32(quad)
    matrix = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(
        ov,
        matrix,
        canvas_size,
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )
    return Image.fromarray(warped)


def composite(base: Image.Image, overlay: Image.Image, xy: tuple[int, int] = (0, 0)) -> Image.Image:
    out = base.convert("RGBA")
    ov = overlay.convert("RGBA")
    if xy == (0, 0) and ov.size == out.size:
        merged = _alpha_over(np.array(out), np.array(ov))
        return Image.fromarray(merged)
    layer = Image.new("RGBA", out.size, (0, 0, 0, 0))
    layer.paste(ov, xy, ov)
    return Image.alpha_composite(out, layer)


@dataclass
class JobSpec:
    client: str
    panel_config: str = "Standard 1 Panel"
    panel_count: int = 1
    product_keys: list[str] = field(default_factory=lambda: ["walk"])
    family: str = "umbrella"
    fabric_name: str = "Black (NRF 001)"
    logo_color_name: str = "Pantone White C"
    request_date: str = ""
    last_update: str = ""
    project_owner: str = "PB"
    print_order: str = ""
    year: int = 2026
    knockout_white: bool = True
    knockout_mode: str = "white"

    def resolved_knockout(self) -> str:
        mode = str(self.knockout_mode or "none")
        if mode in {"white", "black", "none"}:
            return mode
        return "white" if self.knockout_white else "none"

    @property
    def fabric_rgb(self) -> tuple[int, int, int]:
        return FABRIC_COLORS.get(self.fabric_name, FABRIC_COLORS["Black (NRF 001)"])

    @property
    def client_label(self) -> str:
        if self.family == "backpack":
            return f"{self.client} ({self.panel_config or 'Upper center'})"
        return f"{self.client} ({self.panel_config})"

    def logo_panels(self, n_canopy: int = 8) -> list[int]:
        """Panel indices that receive the client mark. Index 0 faces the camera."""
        count = max(1, min(int(self.panel_count), n_canopy))
        if count == 1:
            return [0]
        if count == 2:
            return [0, 4]
        if count == 4:
            return [0, 2, 4, 6]
        return list(range(n_canopy))


class MockupRenderer:
    """Compose Front / Top / Sleeve / Flat Pattern views from centimetre maps."""

    def __init__(self, px_per_cm: float = 20.0) -> None:
        self.px_per_cm = float(px_per_cm)
        TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

    def cm(self, value: float) -> int:
        return max(1, int(round(value * self.px_per_cm)))

    # ------------------------------------------------------------------ logo
    def prepare_logo(
        self,
        logo: Image.Image,
        knockout: bool | str = True,
        fill_rgb: tuple[int, int, int] | None = None,
    ) -> Image.Image:
        """Isolate the mark and fill it with White C, Black C, or a given print color."""
        img = logo.convert("RGBA")
        if knockout is True:
            mode = "white"
        elif knockout is False:
            mode = "none"
        else:
            mode = str(knockout or "none")
        if fill_rgb is None and mode not in {"white", "black"}:
            return img
        arr = np.array(img)
        rgb = arr[:, :, :3].astype(np.float32)
        alpha = arr[:, :, 3].astype(np.float32) / 255.0
        lum = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
        opaque = alpha > 0.08
        if not np.any(opaque):
            return img

        bright = opaque & (lum >= 155)
        dark = opaque & (lum <= 95)
        n_opaque = max(int(opaque.sum()), 1)
        bright_ratio = float(bright.sum()) / n_opaque
        fill = fill_rgb or (PANTONE_WHITE_C if mode == "white" else PANTONE_BLACK_C)
        if bright.any() and dark.any():
            ink = bright if bright_ratio < 0.55 else dark
        elif dark.any() and not bright.any():
            ink = dark
        else:
            ink = bright if bright.any() else opaque

        ink = self._drop_border_background(ink)

        out = np.zeros_like(arr)
        out[:, :, 0] = int(fill[0])
        out[:, :, 1] = int(fill[1])
        out[:, :, 2] = int(fill[2])
        out[:, :, 3] = np.clip(np.where(ink, alpha, 0.0) * 255.0, 0, 255).astype(np.uint8)
        prepared = Image.fromarray(out)
        bbox = prepared.getchannel("A").getbbox()
        return prepared.crop(bbox) if bbox else prepared

    @staticmethod
    def _drop_border_background(ink: np.ndarray) -> np.ndarray:
        """Drop opaque regions that touch the canvas edge (uploaded background plates)."""
        mask = ink.astype(np.uint8) * 255
        if mask.max() == 0:
            return ink
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if n <= 1:
            return ink
        height, width = mask.shape
        keep = np.zeros(n, dtype=bool)
        for idx in range(1, n):
            x = int(stats[idx, cv2.CC_STAT_LEFT])
            y = int(stats[idx, cv2.CC_STAT_TOP])
            w = int(stats[idx, cv2.CC_STAT_WIDTH])
            h = int(stats[idx, cv2.CC_STAT_HEIGHT])
            if x > 0 and y > 0 and x + w < width and y + h < height:
                keep[idx] = True
        if not keep[1:].any():
            largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            keep[largest] = True
        trimmed = np.zeros_like(ink, dtype=bool)
        for idx in range(1, n):
            if keep[idx]:
                trimmed |= labels == idx
        return trimmed

    def _fit_logo(self, logo: Image.Image, max_w: int, max_h: int) -> Image.Image:
        """Uniform fit: scale = min(max_w/w, max_h/h). Never stretches glyphs."""
        return fit_logo_uniform(logo, max_w, max_h)

    # ---------------------------------------------------- backpack fabric tint
    def recolor_backpack_page(
        self,
        page: Image.Image,
        fabric_rgb: tuple[int, int, int],
    ) -> Image.Image | None:
        """Tint Venture Dry Pack photo + line-art via pre-cut alpha masks.

        Uses ``backpack_mask.png`` / ``backpack_lineart_mask.png`` so the coat,
        wall, and worksheet paper stay untouched — no runtime polygon fills.

        Returns ``None`` if masks are missing or tinting fails so the caller can
        fall back without crashing the Streamlit session.
        """
        black = FABRIC_COLORS.get("Black (NRF 001)", (35, 35, 35))
        if fabric_rgb == black:
            return page
        try:
            out = page.convert("RGBA")
            applied = False
            photo_mask = _load_alpha_mask(BACKPACK_PHOTO_MASK, out.size, feather=True)
            if photo_mask is not None:
                out = tint_with_alpha_mask(out, fabric_rgb, photo_mask, mode="photo")
                applied = True
                del photo_mask
            line = _load_alpha_mask(BACKPACK_LINEART_MASK, out.size)
            if line is not None:
                out = tint_with_alpha_mask(out, fabric_rgb, line, mode="flat")
                applied = True
                del line
            return out if applied else None
        except Exception:
            print("Renderer Error:", traceback.format_exc(), flush=True)
            return page

    # ----------------------------------------------------------- WM brand mark
    def weatherman_mark(self, size: int, fill: tuple[int, int, int] = WHITE, bg=NAVY) -> Image.Image:
        """Official 2×2 solid canopy cups in a navy circle (not the four-ring clover)."""
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        pad = size * 0.02
        draw.ellipse((pad, pad, size - 1 - pad, size - 1 - pad), fill=bg + (255,))
        grid = size * 0.44
        gap = max(2.0, size * 0.04)
        cell = (grid - gap) / 2
        origin = (size - grid) / 2
        ink = fill + (255,)
        for col in range(2):
            for row in range(2):
                x0 = origin + col * (cell + gap)
                y0 = origin + row * (cell + gap)
                x1 = x0 + cell
                y1 = y0 + cell
                radius = cell / 2
                if row == 0:
                    draw.rectangle((x0, y0, x1, y0 + radius + 1), fill=ink)
                    draw.ellipse((x0, y1 - 2 * radius, x1, y1), fill=ink)
                else:
                    draw.ellipse((x0, y0, x1, y0 + 2 * radius), fill=ink)
                    draw.rectangle((x0, y1 - radius - 1, x1, y1), fill=ink)
        return img

    # ---------------------------------------------------------- panel geometry
    def panel_polygon(self, product_key: str) -> list[tuple[int, int]]:
        spec = PRODUCT_CATALOG[product_key]["panel"]
        h = self.cm(spec["height_cm"])
        bottom = self.cm(spec["bottom_cm"])
        top = self.cm(spec["top_cm"])
        if spec["shape"] == "triangle" or top <= 1:
            return [(bottom // 2, 0), (bottom, h), (0, h)]
        inset = (bottom - top) // 2
        return [(inset, 0), (inset + top, 0), (bottom, h), (0, h)]

    def panel_canvas_size(self, product_key: str) -> tuple[int, int]:
        spec = PRODUCT_CATALOG[product_key]["panel"]
        return self.cm(spec["bottom_cm"]), self.cm(spec["height_cm"])

    def artwork_box(self, product_key: str) -> tuple[int, int, int, int]:
        """Return (x, y, w, h) of the 21.6 × 10 cm artwork bound on the flat panel."""
        spec = PRODUCT_CATALOG[product_key]["panel"]
        pw, ph = self.panel_canvas_size(product_key)
        art_w = self.cm(spec["artwork_width_cm"])
        art_h = self.cm(spec["artwork_height_cm"])
        logo_h = self.cm(spec["logo_height_cm"])
        offset = self.cm(spec["logo_bottom_offset_cm"])
        # Bound sits above the hem; logo is bottom-aligned inside the 10 cm zone.
        x = (pw - art_w) // 2
        bottom_y = ph - offset
        y = bottom_y - art_h
        # Prefer the measured 6 cm logo height, still clipped to the 10 cm bound.
        _ = logo_h
        return x, y, art_w, art_h

    def render_panel_sample(
        self,
        product_key: str,
        fabric_rgb: tuple[int, int, int],
        logo: Image.Image | None,
        knockout: bool = True,
        annotated: bool = False,
    ) -> Image.Image:
        spec = PRODUCT_CATALOG[product_key]["panel"]
        w, h = self.panel_canvas_size(product_key)
        poly = self.panel_polygon(product_key)
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.polygon(poly, fill=fabric_rgb + (255,))
        # subtle inner seam
        inset = [
            (p[0] + (w / 2 - p[0]) * 0.03, p[1] + (2 - p[1]) * 0.02 if p[1] < h / 2 else p[1] - 2)
            for p in poly
        ]
        draw.line(inset + [inset[0]], fill=shade_color(fabric_rgb, 1.25) + (180,), width=max(2, w // 180))

        if logo is not None:
            mark = self.prepare_logo(logo, knockout)
            ax, ay, aw, ah = self.artwork_box(product_key)
            logo_h = self.cm(spec["logo_height_cm"])
            fitted = self._fit_logo(mark, aw, min(ah, logo_h))
            lx = ax + (aw - fitted.width) // 2
            ly = ay + ah - fitted.height
            img.paste(fitted, (lx, ly), fitted)

        if annotated:
            img = self._annotate_panel(img, product_key, poly)
        return img

    def render_logo_layer(
        self,
        product_key: str,
        logo: Image.Image | None,
        knockout: bool = True,
    ) -> Image.Image:
        """Transparent panel canvas with the mark in the 21.6 × 10 cm bound."""
        w, h = self.panel_canvas_size(product_key)
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        if logo is None:
            return layer
        spec = PRODUCT_CATALOG[product_key]["panel"]
        mark = self.prepare_logo(logo, knockout)
        ax, ay, aw, ah = self.artwork_box(product_key)
        fitted = self._fit_logo(mark, aw, min(ah, self.cm(spec["logo_height_cm"])))
        lx = ax + (aw - fitted.width) // 2
        ly = ay + ah - fitted.height
        layer.paste(fitted, (lx, ly), fitted)
        return layer

    def _annotate_panel(self, panel: Image.Image, product_key: str, poly) -> Image.Image:
        spec = PRODUCT_CATALOG[product_key]["panel"]
        pad = self.cm(8)
        canvas = Image.new("RGBA", (panel.width + pad * 2, panel.height + pad), HEADER_BG + (255,))
        canvas.paste(panel, (pad, 0), panel)
        draw = ImageDraw.Draw(canvas)
        font = _font("sans", max(14, self.cm(0.7)))
        navy = NAVY + (255,)

        def label(xy, text):
            draw.text(xy, text, font=font, fill=navy)

        label((pad, panel.height + 4), f"{spec['bottom_cm']} cm")
        if spec["shape"] == "trapezoid":
            label((pad + (panel.width - self.cm(spec["top_cm"])) // 2, 4), f"{spec['top_cm']} cm")
        label((4, panel.height // 2), f"{spec['height_cm']} cm")
        return canvas

    # -------------------------------------------------------------- 3D canopy
    def _canopy_array(
        self,
        width: int,
        height: int,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        fabric: tuple[int, int, int],
        n_panels: int = 8,
    ) -> np.ndarray:
        yy, xx = np.ogrid[0:height, 0:width]
        nx = (xx - cx) / max(rx, 1)
        ny = (yy - cy) / max(ry, 1)
        r2 = nx * nx + ny * ny
        mask = r2 <= 1.0
        light = 0.52 + 0.48 * np.clip(-0.4 * nx - 0.55 * ny + 0.12, -1.0, 1.0)
        ang = (np.degrees(np.arctan2(ny, nx)) + 360.0) % 360.0
        # Front panel (index 0) is centered at 90° (down, toward the handle).
        rel = (ang - 90.0 + (180.0 / n_panels) + 360.0) % (360.0 / n_panels)
        half = 180.0 / n_panels
        seam = np.abs(rel - half)
        seam_dark = 0.70 + 0.30 * (seam / half)
        shade = np.clip(light * seam_dark, 0.18, 1.15)
        rgba = np.zeros((height, width, 4), dtype=np.uint8)
        for i, channel in enumerate(fabric):
            rgba[:, :, i] = np.where(mask, np.clip(channel * shade, 0, 255), 0).astype(np.uint8)
        rgba[:, :, 3] = np.where(mask, 255, 0).astype(np.uint8)
        return rgba

    @staticmethod
    def _upright_gore_quad(
        inner_a: tuple[float, float],
        inner_b: tuple[float, float],
        outer_a: tuple[float, float],
        outer_b: tuple[float, float],
    ) -> list[tuple[float, float]]:
        """Return TL, TR, BR, BL with the mark's head toward the ferrule and baseline at the hem.

        Source artwork is upright on the flat panel (narrow ferrule edge at the top, hem at
        the bottom). Mapping source-top → inner and source-bottom → outer keeps 'Proper'
        readable the same way as the official Front / Top worksheets.

        Left/right follows the gore's own tangent (cross product of inner→outer) so the
        quad never winds backwards — a reversed winding was flipping the word 180°.
        """
        inner_m = ((inner_a[0] + inner_b[0]) * 0.5, (inner_a[1] + inner_b[1]) * 0.5)
        outer_m = ((outer_a[0] + outer_b[0]) * 0.5, (outer_a[1] + outer_b[1]) * 0.5)
        radial_x = outer_m[0] - inner_m[0]
        radial_y = outer_m[1] - inner_m[1]
        # Screen-space left of the radial (y grows downward): (-radial_y, radial_x).
        side = -radial_y * (inner_a[0] - inner_m[0]) + radial_x * (inner_a[1] - inner_m[1])
        if side >= 0:
            inner_l, outer_l = inner_a, outer_a
            inner_r, outer_r = inner_b, outer_b
        else:
            inner_l, outer_l = inner_b, outer_b
            inner_r, outer_r = inner_a, outer_a
        return [inner_l, inner_r, outer_r, outer_l]

    def _front_panel_quad(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        n_panels: int,
        panel_index: int,
        inner: float = 0.42,
        outer: float = 0.98,
    ) -> list[tuple[float, float]]:
        span = 360.0 / n_panels
        # Panel 0 faces the camera (south / toward the handle), matching canopy shading.
        center_deg = 90.0 + panel_index * span
        a0 = math.radians(center_deg - span / 2)
        a1 = math.radians(center_deg + span / 2)

        def pt(t, ang):
            return (cx + rx * t * math.cos(ang), cy + ry * t * math.sin(ang))

        return self._upright_gore_quad(pt(inner, a0), pt(inner, a1), pt(outer, a0), pt(outer, a1))

    def render_front_view(
        self,
        product_key: str,
        fabric_rgb: tuple[int, int, int],
        logo: Image.Image | None,
        panel_indices: list[int],
        knockout: bool = True,
        size: tuple[int, int] = (1100, 900),
    ) -> Image.Image:
        w, h = size
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        cx, cy = w / 2, h * 0.36
        rx, ry = w * 0.40, h * 0.30
        n = int(PRODUCT_CATALOG[product_key]["canopy_panels"])

        canopy = Image.fromarray(self._canopy_array(w, h, cx, cy, rx, ry, fabric_rgb, n))
        canvas = Image.alpha_composite(canvas, canopy)

        # rim + ferrule (light piping matches the official Walk front view)
        draw = ImageDraw.Draw(canvas)
        piping = (236, 236, 232, 255) if sum(fabric_rgb) < 140 else shade_color(fabric_rgb, 0.45) + (255,)
        draw.ellipse(
            (cx - rx, cy - ry, cx + rx, cy + ry),
            outline=piping,
            width=max(3, w // 220),
        )
        ferrule_r = max(6, int(min(rx, ry) * 0.04))
        draw.ellipse(
            (cx - ferrule_r, cy - ferrule_r, cx + ferrule_r, cy + ferrule_r),
            fill=(210, 210, 210, 255),
            outline=(120, 120, 120, 255),
        )

        if logo is not None:
            layer = self.render_logo_layer(product_key, logo, knockout)
            for idx in panel_indices:
                quad = self._front_panel_quad(cx, cy, rx, ry, n, idx)
                warped = warp_to_quad(layer, (w, h), quad)
                canvas = Image.alpha_composite(canvas, warped)

        # shaft + handle
        shaft_x = int(cx)
        shaft_top = int(cy + ry * 0.15)
        shaft_bot = int(h * 0.78)
        draw = ImageDraw.Draw(canvas)
        draw.line((shaft_x, shaft_top, shaft_x, shaft_bot), fill=(90, 90, 90, 255), width=max(4, w // 140))
        handle_color = (40, 32, 28, 255) if product_key == "golf_essential" else (28, 28, 32, 255)
        hw = max(18, w // 28)
        hh = max(28, h // 22)
        draw.rounded_rectangle(
            (shaft_x - hw // 2, shaft_bot - 8, shaft_x + hw // 2, shaft_bot + hh),
            radius=hw // 3,
            fill=handle_color,
        )
        return canvas

    def render_top_view(
        self,
        product_key: str,
        fabric_rgb: tuple[int, int, int],
        logo: Image.Image | None,
        panel_indices: list[int],
        knockout: bool = True,
        size: tuple[int, int] = (1000, 1000),
    ) -> Image.Image:
        """Schematic top view matching the official worksheet: logo at 3 o'clock."""
        w, h = size
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        cx, cy = w / 2, h / 2
        r = min(w, h) * 0.32
        n = int(PRODUCT_CATALOG[product_key]["canopy_panels"])
        layout = PRODUCT_CATALOG[product_key].get("worksheet_layout") or "stick"
        logo_idx = panel_indices[0] if panel_indices else 0

        def vertex(i: int) -> tuple[float, float]:
            # Panel 0 is east (3 o'clock), as on the official Walk / Golf top diagrams.
            span = 360.0 / n
            ang = math.radians(-span / 2 + i * span)
            return (cx + r * math.cos(ang), cy + r * math.sin(ang))

        verts = [vertex(i) for i in range(n)]
        line = (168, 168, 172, 255)
        fill_idle = (232, 232, 228, 255)
        fill_logo = fabric_rgb + (255,)

        for i in range(n):
            poly = [(cx, cy), verts[i], verts[(i + 1) % n]]
            draw.polygon(poly, fill=fill_logo if i == logo_idx else fill_idle, outline=line)

        if logo is not None:
            # Official top diagrams keep the company mark upright and horizontal
            # on the 3 o'clock gore (a landscape block, not a radially spun word).
            mark = self.prepare_logo(logo, knockout)
            for idx in panel_indices:
                a0 = verts[idx]
                a1 = verts[(idx + 1) % n]
                mx = (a0[0] + a1[0]) / 2
                my = (a0[1] + a1[1]) / 2
                px = cx + (mx - cx) * 0.62
                py = cy + (my - cy) * 0.62
                chord = math.hypot(a1[0] - a0[0], a1[1] - a0[1])
                fitted = self._fit_logo(mark, max(24, int(chord * 0.72)), max(16, int(r * 0.10)))
                canvas.paste(
                    fitted,
                    (int(px - fitted.width / 2), int(py - fitted.height / 2)),
                    fitted,
                )
            draw = ImageDraw.Draw(canvas)

        for v in verts:
            draw.line((cx, cy, v[0], v[1]), fill=line, width=2)
        draw.polygon(verts, outline=line)
        draw.ellipse((cx - 7, cy - 7, cx + 7, cy + 7), fill=(220, 220, 220, 255), outline=line)

        def panel_point(index: int, t: float) -> tuple[float, float]:
            a0, a1 = verts[index], verts[(index + 1) % n]
            mx = (a0[0] + a1[0]) / 2
            my = (a0[1] + a1[1]) / 2
            return (cx + (mx - cx) * t, cy + (my - cy) * t)

        # Closing straps: two adjacent north / north-west panels (official ~10–12 o'clock).
        strap_color = shade_color(fabric_rgb, 0.82) + (255,)
        strap_pts = []
        for i in (5, 6):
            sx, sy = panel_point(i % n, 0.72)
            box = (sx - 14, sy - 6, sx + 14, sy + 6)
            draw.rounded_rectangle(box, radius=3, fill=strap_color, outline=line)
            strap_pts.append((sx, sy))

        # WM canopy logo at 6 o'clock (south), matching the official callout.
        wm_i = 2 % n
        wx, wy = panel_point(wm_i, 0.78)
        mark_size = max(28, int(min(w, h) * 0.055))
        mark = self.weatherman_mark(mark_size, fill=WHITE, bg=fabric_rgb)
        canvas.paste(mark, (int(wx - mark_size / 2), int(wy - mark_size / 2)), mark)

        font = _font("sans", max(18, int(min(w, h) * 0.028)))
        navy = NAVY + (255,)

        def leader(anchor: tuple[float, float], text_xy: tuple[float, float], text: str, align: str = "left"):
            ax, ay = anchor
            tx, ty = text_xy
            draw.line((ax, ay, tx, ty), fill=navy, width=2)
            draw.ellipse((ax - 4, ay - 4, ax + 4, ay + 4), fill=navy)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            draw.text((tx if align == "left" else tx - tw, ty - 8), text, font=font, fill=navy)

        lx, ly = panel_point(logo_idx, 0.62)
        if layout == "golf":
            leader((lx, ly), (cx + r + 36, cy - 8), "Logo")
            leader(strap_pts[1], (cx - 40, cy - r - 36), "SELF FABRIC Closing Strap", align="right")
            leader((wx, wy), (cx - 20, cy + r + 40), "WM Logo", align="right")
        else:
            leader((lx, ly), (cx + r + 28, cy - 10), "Company Logo")
            leader(strap_pts[1], (cx - 24, cy - r - 40), "Closing Straps", align="right")
            leader((wx, wy), (cx + 12, cy + r + 36), "New WM Canopy Logo")
        return canvas

    def render_sleeve(
        self,
        product_key: str,
        fabric_rgb: tuple[int, int, int],
        logo: Image.Image | None,
        knockout: bool = True,
        view: str = "right",
        size: tuple[int, int] = (320, 980),
    ) -> Image.Image:
        """view: left | right | flat | closed."""
        spec = PRODUCT_CATALOG[product_key]["sleeve"]
        w, h = size
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        if view == "flat":
            body = (int(w * 0.12), int(h * 0.04), int(w * 0.88), int(h * 0.96))
            draw.rectangle(body, fill=fabric_rgb + (255,))
        else:
            # Tapered sleeve: wider at the opening (top), narrower at the handle.
            top_w = w * (0.42 if view == "closed" else 0.38)
            bot_w = w * 0.22
            cy_pad = h * 0.04
            poly = [
                (w / 2 - top_w, cy_pad),
                (w / 2 + top_w, cy_pad),
                (w / 2 + bot_w, h * 0.92),
                (w / 2 - bot_w, h * 0.92),
            ]
            draw.polygon(poly, fill=fabric_rgb + (255,))
            draw.ellipse(
                (w / 2 - top_w, cy_pad - 12, w / 2 + top_w, cy_pad + 18),
                fill=shade_color(fabric_rgb, 1.15) + (255,),
            )
            handle_w = w * 0.10
            draw.rounded_rectangle(
                (w / 2 - handle_w, h * 0.90, w / 2 + handle_w, h * 0.98),
                radius=8,
                fill=(36, 30, 26, 255),
            )

        # WM mark near the hem
        mark_size = max(28, int(w * 0.22))
        mark = self.weatherman_mark(mark_size, fill=WHITE, bg=fabric_rgb)
        hem_y = int(h * 0.82) if view != "flat" else int(h * 0.88)
        img.paste(mark, ((w - mark_size) // 2, hem_y), mark)

        place_client = spec.get("client_logo_on_sleeve", product_key == "golf_essential")
        if view == "left":
            place_client = False
        if logo is not None and place_client:
            prepared = self.prepare_logo(logo, knockout)
            logo_h = self.cm(spec["logo_height_cm"])
            offset = self.cm(spec["logo_bottom_offset_cm"])
            # Scale centimetre sleeve mapping into this pixel height (~70 cm tall sleeve).
            sleeve_cm = 70.0
            px_per = h / sleeve_cm
            target_h = max(20, int(spec["logo_height_cm"] * px_per))
            target_off = int(spec["logo_bottom_offset_cm"] * px_per)
            _ = (logo_h, offset)
            fitted = self._fit_logo(prepared, int(w * 0.55), target_h)
            rotated = fitted.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)
            lx = (w - rotated.width) // 2
            ly = h - target_off - rotated.height - int(h * 0.10)
            img.paste(rotated, (lx, ly), rotated)
        return img.filter(ImageFilter.SMOOTH)

    def render_all_views(
        self,
        job: JobSpec,
        logo: Image.Image | None,
        export: bool = False,
    ) -> dict[str, Image.Image]:
        views: dict[str, Image.Image] = {}
        for key in job.product_keys:
            if key not in PRODUCT_CATALOG:
                continue
            n = int(PRODUCT_CATALOG[key]["canopy_panels"])
            panels = job.logo_panels(n)
            prefix = key
            front_size = (1400, 1100) if export else (900, 720)
            top_size = (1100, 1100) if export else (720, 720)
            sleeve_size = (360, 1100) if export else (240, 720)
            mode = job.resolved_knockout()
            views[f"{prefix}_front"] = self.render_front_view(
                key, job.fabric_rgb, logo, panels, mode, front_size
            )
            views[f"{prefix}_top"] = self.render_top_view(
                key, job.fabric_rgb, logo, panels, mode, top_size
            )
            views[f"{prefix}_panel"] = self.render_panel_sample(
                key, job.fabric_rgb, logo, mode, annotated=False
            )
            views[f"{prefix}_sleeve_left"] = self.render_sleeve(
                key, job.fabric_rgb, logo, mode, "left", sleeve_size
            )
            views[f"{prefix}_sleeve_right"] = self.render_sleeve(
                key, job.fabric_rgb, logo, mode, "right", sleeve_size
            )
            views[f"{prefix}_sleeve_flat"] = self.render_sleeve(
                key, job.fabric_rgb, logo, mode, "flat", (420, 1100) if export else (280, 720)
            )
            views[f"{prefix}_sleeve_closed"] = self.render_sleeve(
                key, job.fabric_rgb, logo, mode, "closed", (300, 700) if export else (200, 480)
            )
        return views

    def ensure_templates(self) -> list[Path]:
        """Write base (logo-less) templates so assets/templates/ is populated."""
        TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        fabric = FABRIC_COLORS["Black (NRF 001)"]
        for key in PRODUCT_CATALOG:
            mapping = {
                f"{key}_front.png": self.render_front_view(key, fabric, None, [0], size=(900, 720)),
                f"{key}_top.png": self.render_top_view(key, fabric, None, [0], size=(720, 720)),
                f"{key}_panel.png": self.render_panel_sample(key, fabric, None),
                f"{key}_sleeve.png": self.render_sleeve(key, fabric, None, view="right", size=(240, 720)),
            }
            for name, image in mapping.items():
                path = TEMPLATE_DIR / name
                image.convert("RGBA").save(path)
                written.append(path)
        mark = self.weatherman_mark(256)
        mark_path = TEMPLATE_DIR / "wm_mark.png"
        mark.save(mark_path)
        written.append(mark_path)
        return written


def fit_logo_uniform(
    logo: Image.Image,
    max_w: int,
    max_h: int,
    *,
    crisp: bool = False,
) -> Image.Image:
    """Scale logo with ``min(max_w/w, max_h/h)`` so kerning and aspect stay intact.

    When ``crisp`` is True, alpha is hardened after resize so LANCZOS fringe
    does not feather the mark into the plate (Artwork callout).
    """
    img = logo.convert("RGBA")
    if img.width < 1 or img.height < 1:
        return img
    scale = min(max(1, int(max_w)) / img.width, max(1, int(max_h)) / img.height)
    if scale >= 0.999 and img.width <= max_w and img.height <= max_h:
        out = img
    else:
        nw = max(1, int(round(img.width * scale)))
        nh = max(1, int(round(nw * img.height / img.width)))
        if nh > max_h:
            nh = max(1, int(max_h))
            nw = max(1, int(round(nh * img.width / img.height)))
        out = img.resize((nw, nh), Image.Resampling.LANCZOS)
    if crisp:
        arr = np.array(out)
        alpha = arr[:, :, 3]
        # Drop soft fringe; keep near-opaque ink fully solid.
        arr[:, :, 3] = np.where(alpha < 96, 0, 255).astype(np.uint8)
        out = Image.fromarray(arr, "RGBA")
    return out


def _load_alpha_mask(
    path: Path,
    size: tuple[int, int],
    *,
    feather: bool = False,
) -> Image.Image | None:
    """Load a static 8-bit ``L`` mask, resized to ``size``, or None if unavailable."""
    try:
        if not path.is_file():
            return None
        with Image.open(path) as mask:
            alpha = mask.convert("L")
        if alpha.size != size:
            if size[0] < 1 or size[1] < 1:
                return None
            alpha = alpha.resize(size, Image.Resampling.BILINEAR)
        if feather:
            alpha = alpha.filter(ImageFilter.GaussianBlur(radius=1))
        return alpha
    except Exception:
        return None


def _mask_bbox(alpha_u8: np.ndarray, threshold: int = 5) -> tuple[int, int, int, int] | None:
    """Return inclusive-exclusive (y0, y1, x0, x1) for pixels above threshold."""
    ys, xs = np.where(alpha_u8 > threshold)
    if ys.size == 0:
        return None
    return int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1


def _match_layer(image: Image.Image, size: tuple[int, int], mode: str) -> Image.Image:
    """Force ``image`` to ``size`` and ``mode`` so Image.composite cannot fail."""
    out = image.convert(mode)
    if out.size != size:
        if size[0] < 1 or size[1] < 1:
            return Image.new(mode, (max(1, size[0]), max(1, size[1])))
        out = out.resize(size, Image.Resampling.BILINEAR)
    return out


def tint_with_alpha_mask(
    page: Image.Image,
    fabric_rgb: tuple[int, int, int],
    alpha_mask: Image.Image,
    *,
    mode: str = "photo",
) -> Image.Image:
    """Tint fabric under a static 8-bit mask. No runtime color rejection.

    ``mode="photo"`` multiplies a solid fabric fill by the source photo RGB,
    then ``Image.composite``s it over the original using the PNG mask only.
    ``mode="flat"`` lifts line-art fills so handles/mesh match the body.

    Only the mask bounding box is processed (full-page blends OOM on Cloud).
    """
    page_rgba = page.convert("RGBA")
    try:
        if page_rgba.width < 1 or page_rgba.height < 1:
            return page_rgba

        photo = page_rgba.convert("RGB")
        alpha_img = _match_layer(alpha_mask, photo.size, "L")

        alpha_u8 = np.ascontiguousarray(np.asarray(alpha_img, dtype=np.uint8))
        bbox = _mask_bbox(alpha_u8)
        if bbox is None:
            return page_rgba
        y0, y1, x0, x1 = bbox
        box = (x0, y0, x1, y1)

        if mode == "flat":
            out = np.array(page_rgba, copy=True)
            if out.ndim != 3 or out.shape[2] < 3:
                return page_rgba
            rgb = out[y0:y1, x0:x1, :3].astype(np.float32)
            a = (alpha_u8[y0:y1, x0:x1].astype(np.float32) / 255.0)[..., None]
            src_a = np.array(FABRIC_COLORS.get("Black (NRF 001)", (35, 35, 35)), dtype=np.float32)
            dst_a = np.array(tuple(int(v) for v in fabric_rgb), dtype=np.float32)
            tinted = np.clip(np.maximum(rgb, src_a) + (dst_a - src_a), 0, 255)
            blended = rgb * (1.0 - a) + tinted * a
            out[y0:y1, x0:x1, :3] = np.clip(blended, 0, 255).astype(np.uint8)
            return Image.fromarray(out, "RGBA")

        roi = _match_layer(photo.crop(box), (max(1, x1 - x0), max(1, y1 - y0)), "RGB")
        size = roi.size
        mask_roi = _match_layer(alpha_img.crop(box), size, "L")
        fabric = tuple(int(v) for v in fabric_rgb)
        solid = Image.new("RGB", size, fabric)
        # Standard multiply: fabric × photo preserves shadow/highlight structure.
        fabric_layer = ImageChops.multiply(solid, roi)
        fabric_layer = _match_layer(fabric_layer, size, "RGB")
        composited = image_composite(fabric_layer, roi, mask_roi)
        page_rgba.paste(composited.convert("RGB"), (x0, y0))
        return page_rgba
    except Exception:
        print("Renderer Error:", traceback.format_exc(), flush=True)
        return page_rgba


def fabric_swatch_names() -> list[str]:
    return list(FABRIC_COLORS.keys())
