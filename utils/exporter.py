"""Production worksheets built from the official Illustrator PDF.

The Proper Brands x WM Umbrella 2026 sheet is the page template. This module
covers the original Proper marks, stamps the current job logo, and rewrites
header fields. Layout, photography, callouts, and pagination stay untouched.
"""

from __future__ import annotations

import traceback
from datetime import date
from io import BytesIO
from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .catalog import fabric_sheet_lines, logo_color_rgb, style_family
from .renderer import (
    FABRIC_COLORS,
    HEADER_BG,
    NAVY,
    JobSpec,
    MockupRenderer,
    fit_logo_uniform,
)

ROOT = Path(__file__).resolve().parent.parent
OFFICIAL_PDF = ROOT / "assets" / "templates" / "official_worksheet.pdf"
OFFICIAL_PAGES = ROOT / "assets" / "templates" / "official"
TEMPLATE_DPI = 144
SCALE = TEMPLATE_DPI / 72.0  # template pixels per PDF point

_FONT_CANDIDATES = (
    ROOT / "assets" / "fonts",
    Path("/usr/share/fonts/truetype/liberation"),
    Path("/usr/share/fonts/liberation"),
    Path("/usr/share/fonts/truetype/liberation2"),
)
_FONT_DIR = next((p for p in _FONT_CANDIDATES if (p / "LiberationSans-Regular.ttf").exists()), _FONT_CANDIDATES[0])

# Official page numbers (1-based) used for each style.
STYLE_PAGES: dict[str, list[int]] = {
    "walk": [1],
    "stick": [1],
    "trek": [1],
    "travel": [1],
    "collapsible": [1],
    "kids": [1],
    "golf_essential": [2, 3, 4],
    "golf_62": [2, 3, 4],
    "golf_68": [2, 3, 4],
    "venture_dry_pack": [1],
}

PAGE_TITLES: dict[int, str] = {
    1: "Walk",
    2: "Golf Essential",
    3: "Graphic sizing",
    4: "Sleeve",
}

BACKPACK_TITLES: dict[int, str] = {
    1: "Venture Dry Pack",
}

# Venture Dry Pack (style 40002) — M13 backpack worksheet, same page size as Walk.
def _cm_box(center_x: float, center_y: float, width_cm: float, height_cm: float) -> tuple[float, float, float, float]:
    """PDF-point box centered on a worksheet anchor (72 pt/in)."""
    w = width_cm / 2.54 * 72.0
    h = height_cm / 2.54 * 72.0
    return (center_x - w / 2.0, center_y - h / 2.0, w, h)


# Venture Dry Pack artwork bounds: 9.2 × 4.5 cm on the line drawing (M13 anchor).
_BACKPACK_ART_W_CM = 9.2
_BACKPACK_ART_H_CM = 4.5
_BACKPACK_DRAW_CENTER = (1041.5, 2275.0)
_BACKPACK_DRAW_BOX = _cm_box(*_BACKPACK_DRAW_CENTER, _BACKPACK_ART_W_CM, _BACKPACK_ART_H_CM)
_dx, _dy, _dw, _dh = _BACKPACK_DRAW_BOX
# Generous cover so the sample M13 (wider than the 9.2×4.5 art bound) is fully cleared.
_BACKPACK_DRAW_COVER = (_dx - 55.0, _dy - 45.0, _dw + 110.0, _dh + 90.0)

BACKPACK_PAGE_SPEC: dict[int, dict] = {
    1: {
        "size_pts": (2125.98, 3259.84),
        "logos": [
            # Front-view photo — calibrated upper pocket panel below zipper seam.
            {
                "box": (556.5, 930.0, 135.0, 32.0),
                "cover": (400, 790, 400, 280),
                "erase": "photo",
                "rotate": 2.5,
            },
            # Artwork callout — full plate edge-to-edge solid fabric (no letterbox bands).
            {
                "box": (1286, 922, 420, 180),
                "cover": (1189, 630, 614, 742.5),
                "erase": "artwork",
                "crisp": True,
                "fit_pad": 0.14,
            },
            # Front-view line drawing — wipe baked sample plate into continuous fabric.
            {
                "box": _BACKPACK_DRAW_BOX,
                "cover": _BACKPACK_DRAW_COVER,
                "erase": "none",
                "clear_default": True,
            },
        ],
        "chip": (1308.0, 58.0, 597.0, 155.0),
        "header_fields": {
            "request_date": (1105, 48, 160, 30),
            "last_update": (1105, 95, 160, 32),
            "project_owner": (1105, 143, 160, 32),
            "print_order": (1105, 190, 160, 32),
        },
        # Higher lum unused for backpack (mask path); kept for umbrella parity docs.
        "recolor_masks": True,
        "colors": {
            "logo_swatch": (56, 2068, 90, 48),
            "logo_label": (155, 2065, 300, 54),
            "fabric_swatch": (56, 1890, 90, 48),
            "fabric_label": (155, 1888, 300, 52),
            "font_pt": 16,
        },
    },
}

# Coordinates are PDF points at 72 dpi (page-1 = 2126×3260, golf = 2126×3544).
# `box` is the fitted logo; `cover` is inpainted so original ink leaves no patch.
PAGE_SPEC: dict[int, dict] = {
    1: {
        "size_pts": (2125.98, 3259.84),
        "logos": [
            # Front canopy: heal original Proper (glyphs + bevels) after recolor.
            {"box": (485, 860, 176, 42), "cover": (475, 852, 200, 58), "erase": "photo"},
            # Closed-sleeve wordmark — clone neighboring fabric after recolor (no rectangle).
            # Cover spans the Weatherman icon + wordmark; stop short of the ferrule.
            {"box": (670, 1410, 170, 24), "cover": (595, 1385, 305, 75), "erase": "sleeve"},
            # Flat panel sample logo band.
            {"box": (758, 2504, 610, 165), "cover": (742, 2488, 644, 200), "erase": "flat"},
        ],
        "chip": (1300, 50, 618, 168),
        "header_fields": {
            "request_date": (1105, 48, 160, 30),
            "last_update": (1105, 95, 160, 32),
            "project_owner": (1105, 143, 160, 32),
            "print_order": (1105, 190, 160, 32),
        },
        "colors": {
            "logo_swatch": (59, 1877, 100, 44),
            "logo_label": (164, 1873, 270, 45),
            "fabric_swatch": (629, 1877, 86, 44),
            "fabric_label": (733, 1873, 340, 45),
            "font_pt": 18,
        },
    },
    2: {
        "size_pts": (2125.98, 3543.84),
        "logos": [
            {"box": (920, 2344, 292, 80), "cover": (900, 2320, 332, 128), "erase": "ink"},
            # Closed / horizontal sleeve wordmark — heal pale ink after recolor.
            {"box": (1248, 3198, 210, 44), "cover": (1190, 3175, 275, 80), "erase": "sleeve"},
        ],
        "chip": (1300, 50, 618, 168),
    },
    3: {
        "size_pts": (2125.98, 3543.84),
        "logos": [
            {"box": (730, 2440, 680, 210), "cover": (710, 2420, 720, 250), "erase": "flat"},
        ],
        "chip": (1300, 50, 618, 168),
        "colors": {
            "logo_swatch": (118, 667, 80, 36),
            "logo_label": (202, 663, 250, 38),
            "fabric_swatch": (118, 506, 72, 35),
            "fabric_label": (202, 502, 280, 38),
            "font_pt": 14,
        },
    },
    4: {
        "size_pts": (2125.98, 3543.84),
        "logos": [
            {"box": (610, 2440, 130, 360), "rotate": 90, "erase": "ink"},
            {"box": (1336, 2440, 130, 360), "rotate": 90, "erase": "ink"},
        ],
        "chip": (1300, 50, 618, 168),
        "colors": {
            "logo_swatch": (1738, 860, 80, 36),
            "logo_label": (1823, 855, 220, 38),
            "fabric_swatch": (1739, 699, 71, 34),
            "fabric_label": (1823, 694, 220, 38),
            "font_pt": 14,
        },
    },
}


def worksheet_filename(client: str, year: int | None = None, family: str = "umbrella") -> str:
    year = year or date.today().year
    safe = " ".join(client.strip().split()) or "Client"
    kind = "Backpack" if family == "backpack" else "Umbrella"
    return f"{safe} x WM {kind} {year} Mockup Designs.pdf"


def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    name = "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"
    path = _FONT_DIR / name
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default()


def _pts(box: tuple[float, ...]) -> tuple[int, ...]:
    return tuple(int(round(v * SCALE)) for v in box)


def _trim_mark(mark: PILImage.Image) -> PILImage.Image:
    bbox = mark.getchannel("A").getbbox()
    return mark.crop(bbox) if bbox else mark


def _strip_mark_backdrop(mark: PILImage.Image) -> PILImage.Image:
    """Drop a solid dark plate behind the mark when contrasting light ink is inside."""
    import numpy as np

    arr = np.array(mark.convert("RGBA"))
    rgb = arr[:, :, :3].astype(np.float32)
    alpha = arr[:, :, 3]
    lum = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    opaque = alpha > 200
    if not opaque.any():
        return mark
    bright = opaque & (lum > 160)
    dark_plate = opaque & (lum < 80)
    # Only strip dark plate if there is BOTH a large dark background container AND bright glyphs inside
    if (
        bright.any()
        and dark_plate.any()
        and float(bright.sum()) > 50
        and float(dark_plate.mean()) > 0.18
        and float(dark_plate.sum()) > 400
    ):
        arr[dark_plate, 3] = 0
        out = PILImage.fromarray(arr, "RGBA")
        bbox = out.getchannel("A").getbbox()
        return out.crop(bbox) if bbox else out
    return mark


def _recolor_ink(mark: PILImage.Image, rgb: tuple[int, int, int]) -> PILImage.Image:
    import numpy as np

    arr = np.array(mark.convert("RGBA"))
    ink = arr[:, :, 3] > 0
    arr[ink, 0] = int(rgb[0])
    arr[ink, 1] = int(rgb[1])
    arr[ink, 2] = int(rgb[2])
    return PILImage.fromarray(arr)


def _pt_xy(x: float, y: float) -> tuple[int, int]:
    return int(round(x * SCALE)), int(round(y * SCALE))


def _outline_mark(
    mark: PILImage.Image,
    outline: tuple[int, int, int],
    width_px: int,
    fill: bool = True,
) -> PILImage.Image:
    """Stroke glyph edges. If fill is False, only the perimeter is drawn."""
    import cv2
    import numpy as np

    width_px = max(1, int(width_px))
    pad = width_px + 1
    src = mark.convert("RGBA")
    canvas = PILImage.new("RGBA", (src.width + pad * 2, src.height + pad * 2), (0, 0, 0, 0))
    canvas.paste(src, (pad, pad), src)
    arr = np.array(canvas)
    alpha = arr[:, :, 3]
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    dilated = cv2.dilate(alpha, kernel, iterations=max(1, width_px))
    ring = cv2.subtract(dilated, alpha)
    out = np.zeros_like(arr)
    out[:, :, 0] = int(outline[0])
    out[:, :, 1] = int(outline[1])
    out[:, :, 2] = int(outline[2])
    out[:, :, 3] = ring
    stroked = PILImage.fromarray(out)
    if fill:
        stroked.alpha_composite(canvas)
    return stroked


class WorksheetExporter:
    """Stamp a job onto the official Weatherman production-worksheet pages."""

    def __init__(self, renderer: MockupRenderer | None = None) -> None:
        self.renderer = renderer or MockupRenderer(px_per_cm=24.0)
        self._pages: dict[tuple[str, int], PILImage.Image] = {}

    def _job_family(self, job: JobSpec) -> str:
        if getattr(job, "family", None):
            return str(job.family)
        for key in job.product_keys:
            fam = style_family(key)
            if fam != "umbrella":
                return fam
        return "umbrella"

    def _page_spec(self, family: str, page_no: int) -> dict:
        if family == "backpack":
            return BACKPACK_PAGE_SPEC[page_no]
        return PAGE_SPEC[page_no]

    def _page_title(self, family: str, page_no: int) -> str:
        if family == "backpack":
            return BACKPACK_TITLES.get(page_no, f"Page {page_no}")
        return PAGE_TITLES.get(page_no, f"Page {page_no}")

    def _template(self, page_no: int, family: str = "umbrella") -> PILImage.Image:
        key = (family, page_no)
        if key not in self._pages:
            if family == "backpack":
                path = OFFICIAL_PAGES / "backpack" / f"page-{page_no}.png"
            else:
                path = OFFICIAL_PAGES / f"page-{page_no}.png"
            if not path.exists():
                raise FileNotFoundError(
                    f"Official worksheet page missing: {path}. "
                    "Place the Illustrator PDF at assets/templates/official_worksheet.pdf "
                    f"and rasterize with: pdftoppm -png -r {TEMPLATE_DPI} ..."
                )
            self._pages[key] = PILImage.open(path).convert("RGBA")
        return self._pages[key].copy()

    def page_plan(self, job: JobSpec) -> list[tuple[int, str]]:
        """Official worksheet pages that will be included for the selected styles."""
        family = self._job_family(job)
        seen: set[int] = set()
        plan: list[tuple[int, str]] = []
        for key in job.product_keys:
            for page_no in STYLE_PAGES.get(key, []):
                if page_no in seen:
                    continue
                seen.add(page_no)
                plan.append((page_no, self._page_title(family, page_no)))
        return plan

    def iter_job_pages(
        self,
        job: JobSpec,
        logo: PILImage.Image | None,
    ):
        """Yield (page_no, title, stamped official page) for the selected styles."""
        mark = None
        if logo is not None:
            fill = None
            if job.logo_color_name != "Match uploaded art":
                fill = logo_color_rgb(job.logo_color_name)
            mark = self.renderer.prepare_logo(logo, job.resolved_knockout(), fill_rgb=fill)
        family = self._job_family(job)
        seen: set[int] = set()
        for key in job.product_keys:
            for page_no in STYLE_PAGES.get(key, []):
                if page_no in seen:
                    continue
                seen.add(page_no)
                yield page_no, self._page_title(family, page_no), self._compose_page(
                    page_no, job, mark, family=family
                )

    def preview_jpegs(
        self,
        job: JobSpec,
        logo: PILImage.Image | None,
        *,
        max_width: int = 1400,
        quality: int = 88,
    ) -> list[tuple[str, bytes]]:
        """Official stamped pages, scaled for the on-screen proof."""
        previews: list[tuple[str, bytes]] = []
        for _page_no, title, page in self.iter_job_pages(job, logo):
            try:
                rgb = page.convert("RGB")
                if rgb.width > max_width:
                    ratio = max_width / rgb.width
                    rgb = rgb.resize(
                        (max_width, max(1, int(rgb.height * ratio))),
                        PILImage.Resampling.LANCZOS,
                    )
                buf = BytesIO()
                rgb.save(buf, format="JPEG", quality=quality, optimize=True)
                previews.append((title, buf.getvalue()))
            except Exception:
                print("Exporter Error:", traceback.format_exc(), flush=True)
        return previews

    def build_pdf(self, job: JobSpec, logo: PILImage.Image | None) -> bytes:
        buffer = BytesIO()
        family = self._job_family(job)
        first_pages = STYLE_PAGES.get(job.product_keys[0], [1]) if job.product_keys else [1]
        w, h = self._page_spec(family, first_pages[0])["size_pts"]
        c = canvas.Canvas(buffer, pagesize=(w, h))
        c.setTitle(worksheet_filename(job.client, job.year, family).replace(".pdf", ""))
        c.setAuthor("Weatherman Virtual Mockup Creator")
        c.setSubject("PRODUCTION WORKSHEET")

        for page_no, _title, page in self.iter_job_pages(job, logo):
            spec = self._page_spec(family, page_no)
            c.setPageSize(spec["size_pts"])
            self._draw_full_page(c, page, spec["size_pts"])
            c.showPage()

        c.save()
        return buffer.getvalue()

    def _compose_page(
        self,
        page_no: int,
        job: JobSpec,
        mark: PILImage.Image | None,
        *,
        family: str = "umbrella",
    ) -> PILImage.Image:
        page = self._template(page_no, family)
        base = page.copy()
        try:
            spec = self._page_spec(family, page_no)
            if family == "backpack":
                # Dynamic front photo logo slot calibrated for Sage / Steel Blue / Black.
                spec = {**spec, "logos": [dict(s) for s in spec["logos"]]}
                for idx, slot in enumerate(spec["logos"]):
                    if str(slot.get("erase") or "") == "photo":
                        spec["logos"][idx] = self.renderer.get_backpack_front_slot(job.fabric_name)
            fabric = job.fabric_rgb
            black = FABRIC_COLORS.get("Black (NRF 001)", (30, 30, 30))
            # Photo/sleeve heals sample already-tinted fabric. Running them before
            # recolor left a gray plate (skipped by the lum<95 shift) and leftover
            # bevels that read as a ghost under the new mark.
            post = {"photo", "sleeve", "plate", "artwork", "none"}
            for slot in spec["logos"]:
                erase = str(slot.get("erase") or "")
                if erase in post or slot.get("clear_default"):
                    continue
                self._erase_slot(page, slot, black)
            # Backpack always runs mask/native-front path (incl. Black base paste).
            if family == "backpack" or spec.get("recolor_masks"):
                tinted = self.renderer.recolor_backpack_page(
                    page,
                    fabric,
                    fabric_name=job.fabric_name,
                )
                if tinted is not None:
                    page = tinted
                elif fabric != black:
                    page = self._recolor_fabric(
                        page,
                        fabric,
                        regions=[(555, 1830, 890, 1280)],
                        max_lum=125,
                    )
            elif fabric != black:
                page = self._recolor_fabric(
                    page,
                    fabric,
                    regions=spec.get("recolor_regions"),
                    polygons=spec.get("recolor_polys"),
                    max_lum=float(spec.get("recolor_max_lum") or 95),
                )
            # Artwork preview: programmatic solid fabric — no letterbox / black base.
            for slot in spec["logos"]:
                if str(slot.get("erase") or "") == "artwork":
                    self._paint_artwork_swatch(page, base, slot, fabric)
            # Sage/Steel native SKU photos have no baked mark — skip photo inpaint.
            # Black base crop still carries sample M13; cleared via _blank_photo_logo_zone.
            fabric_key = " ".join(str(job.fabric_name or "").lower().split())
            skip_photo_erase = family == "backpack" and (
                "sage" in fabric_key or "steel" in fabric_key or "black" in fabric_key
            )
            for slot in spec["logos"]:
                erase = str(slot.get("erase") or "")
                if erase not in {"photo", "sleeve", "plate"}:
                    continue
                if skip_photo_erase and erase == "photo":
                    continue
                self._erase_slot(page, slot, fabric)
            # Always wipe backpack default marks on line art — even with no upload.
            if family == "backpack":
                for slot in spec["logos"]:
                    erase = str(slot.get("erase") or "")
                    cover = slot.get("cover") or slot.get("box")
                    if not cover:
                        continue
                    if slot.get("clear_default"):
                        self._clear_lineart_logo_zone(
                            page,
                            cover,
                            fabric,
                            box=slot.get("box"),
                        )
                    elif erase == "photo" and "black" in fabric_key:
                        self._blank_photo_logo_zone(page, cover, fabric)
            if mark is not None:
                for slot in spec["logos"]:
                    self._stamp_logo(page, slot, mark, fabric, erase=False)
            self._stamp_colors(page, spec, job)
            self._stamp_header(page, spec, job)
            return page
        except Exception:
            print("Exporter Error:", traceback.format_exc(), flush=True)
            return base

    def _erase_slot(
        self,
        page: PILImage.Image,
        slot: dict,
        fabric: tuple[int, int, int],
    ) -> None:
        """Remove original artwork in a slot before fabric recolor / restamp."""
        erase = str(slot.get("erase") or "ink")
        cover = slot.get("cover") or slot.get("box")
        if not cover or erase in {"none", ""}:
            return
        if erase == "photo":
            self._inpaint_cover(page, cover)
        elif erase == "sleeve":
            # Horizontal photo sleeve: heal pale glyphs only so fabric shading stays.
            self._heal_pale_rows(page, cover)
        elif erase == "ink":
            self._erase_pale_on_fabric(page, cover, fabric, fill=False)
        elif erase == "flat":
            self._erase_pale_on_fabric(page, cover, fabric, fill=True)
        elif erase == "block":
            self._fill_cover(page, cover, fabric)
        elif erase == "artwork":
            pass  # Composited after recolor in _compose_page.
        elif erase == "plate":
            plate = slot.get("plate") or (48, 48, 50)
            self._fill_cover(page, cover, tuple(int(v) for v in plate))
        elif erase == "schematic":
            self._clear_schematic_fill(page, cover, (255, 255, 255))

    def _stamp_logo(
        self,
        page: PILImage.Image,
        slot: dict,
        mark: PILImage.Image,
        fabric: tuple[int, int, int],
        *,
        erase: bool = True,
    ) -> None:
        if erase:
            self._erase_slot(page, slot, fabric)
        if slot.get("stamp") is False or "box" not in slot:
            return
        erase_mode = str(slot.get("erase") or "")
        # Artwork swatch is painted in _paint_artwork_swatch — only stamp the logo here.
        if erase_mode not in {"artwork"}:
            if erase_mode in {"block", "plate"}:
                cover = slot.get("cover") or slot.get("box")
                if cover:
                    fill = fabric
                    if erase_mode == "plate":
                        fill = tuple(int(v) for v in (slot.get("plate") or fabric))
                    self._fill_cover(page, cover, fill)

        x, y, w, h = _pts(slot["box"])
        rotate = float(slot.get("rotate") or 0)
        art = _trim_mark(mark.convert("RGBA"))
        # Force fully transparent backdrop — keep ink only (no dark plate in SVG).
        art = _strip_mark_backdrop(art)
        if art.getchannel("A").getextrema()[1] < 1:
            return
        ink = slot.get("ink")
        if ink:
            art = _recolor_ink(art, tuple(int(v) for v in ink))
        if rotate:
            art = art.rotate(rotate, expand=True, resample=PILImage.Resampling.BICUBIC)
        if art.width < 1 or art.height < 1:
            return
        outline = slot.get("outline")
        outline_px = max(1, int(round(float(slot.get("outline_pt") or 0) * SCALE))) if outline else 0

        # Contrast detection and auto-outline safeguard
        if not outline:
            import numpy as np

            arr_art = np.array(art)
            alpha_mask = arr_art[:, :, 3] > 60
            if alpha_mask.any():
                ink_rgb = arr_art[alpha_mask, :3].mean(axis=0)
                ink_lum = 0.2126 * float(ink_rgb[0]) + 0.7152 * float(ink_rgb[1]) + 0.0722 * float(ink_rgb[2])
            else:
                ink_lum = 255.0

            slot_bg = (244, 244, 245) if erase_mode == "artwork" else fabric
            bg_lum = 0.2126 * float(slot_bg[0]) + 0.7152 * float(slot_bg[1]) + 0.0722 * float(slot_bg[2])
            delta_lum = abs(ink_lum - bg_lum)

            if delta_lum < 48.0:
                outline_px = max(1, int(round(1.0 * SCALE)))
                outline = (255, 255, 255) if ink_lum < 128.0 else (120, 120, 120)

        pad = float(slot.get("fit_pad") or 0.0)
        fit_w = max(1, int(round((w - outline_px * 2) * (1.0 - pad))))
        fit_h = max(1, int(round((h - outline_px * 2) * (1.0 - pad))))
        # Uniform scale: min(fit_w/w, fit_h/h) — preserves kerning / glyph aspect.
        art = fit_logo_uniform(art, fit_w, fit_h, crisp=bool(slot.get("crisp")))
        if outline:
            art = _outline_mark(
                art,
                tuple(int(v) for v in outline),
                outline_px,
                fill=not bool(slot.get("outline_only")),
            )
        quad = slot.get("quad")
        if quad and len(quad) == 4:
            import cv2
            import numpy as np

            # Warp into the quad's bounding box only — a full-page warpPerspective
            # (~4252×6520 RGBA) spikes RSS past Streamlit Cloud's memory limit.
            dst = np.float32([_pt_xy(float(px), float(py)) for px, py in quad])
            x0 = max(0, int(np.floor(float(dst[:, 0].min()))) - 1)
            y0 = max(0, int(np.floor(float(dst[:, 1].min()))) - 1)
            x1 = min(page.width, int(np.ceil(float(dst[:, 0].max()))) + 1)
            y1 = min(page.height, int(np.ceil(float(dst[:, 1].max()))) + 1)
            if x1 - x0 < 2 or y1 - y0 < 2:
                return
            local = dst.copy()
            local[:, 0] -= x0
            local[:, 1] -= y0
            src_w, src_h = art.size
            src = np.float32([[0, 0], [src_w, 0], [src_w, src_h], [0, src_h]])
            matrix = cv2.getPerspectiveTransform(src, local)
            warped = cv2.warpPerspective(
                np.array(art),
                matrix,
                (x1 - x0, y1 - y0),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0, 0),
            )
            overlay = PILImage.fromarray(warped)
            page.paste(overlay, (x0, y0), overlay)
            return
        px = x + (w - art.width) // 2
        py = y + (h - art.height) // 2
        page.paste(art, (px, py), art)

    def _inpaint_cover(self, page: PILImage.Image, cover: tuple[float, float, float, float]) -> None:
        """Erase original photo-slot art (pale ink plus beveled edges) after recolor.

        Grows a mask from pale glyphs into nearby outliers so baked-in bevels go
        with the letters. A full-rect mask or a median flood left a fabric patch.
        Must run after fabric recolor so leftover ink is compared to the new color.
        """
        import cv2
        import numpy as np

        x, y, w, h = _pts(cover)
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(page.width, x + w), min(page.height, y + h)
        if x1 - x0 < 12 or y1 - y0 < 12:
            return
        crop = np.array(page.crop((x0, y0, x1, y1)))
        rgb = crop[:, :, :3]
        lum = rgb.mean(axis=2).astype(np.float32)
        paper = (cv2.blur(lum, (51, 51)) > 232) & (lum > 240)
        body = ~paper
        if not body.any():
            return
        local = float(np.median(lum[body]))
        pale = body & (lum > local + 14)
        grow = body & ((lum > local + 8) | (lum < local - 12) | (np.abs(lum - local) > 16))
        seed = pale.astype(np.uint8) * 255
        if int(seed.max()) == 0:
            seed = (body & (lum < local - 12)).astype(np.uint8) * 255
        grow_u8 = grow.astype(np.uint8) * 255
        kernel = np.ones((3, 3), np.uint8)
        mask = seed
        for _ in range(14):
            nxt = cv2.bitwise_and(cv2.dilate(mask, kernel, iterations=1), grow_u8)
            nxt = cv2.bitwise_or(nxt, mask)
            if int(cv2.countNonZero(cv2.subtract(nxt, mask))) == 0:
                break
            mask = nxt
        if int(mask.max()) == 0:
            return
        mask = cv2.dilate(mask, kernel, iterations=3)
        mask[paper] = 0
        near = cv2.dilate(mask, np.ones((11, 11), np.uint8), iterations=2) > 0
        rgb2 = rgb.astype(np.float32)
        for row in range(lum.shape[0]):
            m = mask[row] > 0
            n = near[row]
            if not (np.any(m) or np.any(n)):
                continue
            keep = (mask[row] == 0) & body[row] & (~n)
            if int(keep.sum()) < 4:
                keep = (mask[row] == 0) & body[row]
            if int(keep.sum()) >= 4:
                fill = np.median(rgb2[row][keep], axis=0)
            elif body[row].any():
                fill = np.median(rgb2[row][body[row]], axis=0)
            else:
                fill = np.median(rgb2[body], axis=0)
            if np.any(m):
                rgb2[row, m] = fill
            row_lum = rgb2[row].mean(axis=1)
            extra = body[row] & n & (np.abs(row_lum - float(fill.mean())) > 6)
            if extra.any():
                rgb2[row, extra] = fill
        crop[:, :, :3] = np.clip(rgb2, 0, 255).astype(np.uint8)
        page.paste(PILImage.fromarray(crop), (x0, y0))

    def _heal_pale_rows(self, page: PILImage.Image, cover: tuple[float, float, float, float]) -> None:
        """Rebuild the closed-sleeve logo band from neighboring fabric shading.

        The official photo has a darker plate plus a beveled white wordmark. Erasing
        only pale pixels left that plate (a visible block on orange, navy, and lilac).
        Each scanline is cloned from fabric immediately left of the slot. The whole
        logo band is replaced (no edge-feather with the original) so the plate and
        beveled Weatherman mark cannot remain as a ghost. Must run after recolor.
        """
        import cv2
        import numpy as np

        x, y, w, h = _pts(cover)
        left_pad = int(40 * SCALE)
        x0 = max(0, x - left_pad)
        y0, y1 = max(0, y), min(page.height, y + h)
        x1 = min(page.width, x + w)
        if x1 - x0 < 12 or y1 - y0 < 8:
            return
        crop = np.array(page.crop((x0, y0, x1, y1)))
        rgb = crop[:, :, :3].astype(np.float32)
        lum = rgb.mean(axis=2)
        paper = (cv2.blur(lum, (51, 51)) > 232) & (lum > 240)
        height, width = lum.shape
        tx0 = x - x0
        if tx0 < 4 or tx0 >= width - 4:
            return
        out = rgb.copy()
        for row in range(height):
            if float(paper[row].mean()) > 0.65:
                continue
            left_band = ~paper[row, :tx0]
            if int(left_band.sum()) < 4:
                continue
            left_lum = lum[row, :tx0][left_band]
            left_med = float(np.median(left_lum))
            left_ok = left_band & (np.abs(lum[row, :tx0] - left_med) < 36)
            if int(left_ok.sum()) < 4:
                left_ok = left_band
            src_idx = np.flatnonzero(left_ok)
            src_idx = src_idx[-min(24, src_idx.size) :]
            out[row, tx0:] = rgb[row, src_idx[np.arange(width - tx0) % src_idx.size]]
        crop[:, :, :3] = np.clip(out, 0, 255).astype(np.uint8)
        page.paste(PILImage.fromarray(crop), (x0, y0))

    def _erase_pale_on_fabric(
        self,
        page: PILImage.Image,
        cover: tuple[float, float, float, float],
        fabric: tuple[int, int, int],
        fill: bool = False,
    ) -> None:
        """Erase white/pale marks that sit on fabric, without touching the page."""
        import cv2
        import numpy as np

        x, y, w, h = _pts(cover)
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(page.width, x + w), min(page.height, y + h)
        if x1 - x0 < 8 or y1 - y0 < 8:
            return
        crop = np.array(page.crop((x0, y0, x1, y1)))
        rgb = crop[:, :, :3]
        lum = rgb.mean(axis=2)
        chroma = rgb.max(axis=2) - rgb.min(axis=2)
        is_fabric = (lum < 190) & ((chroma > 16) | (lum < 95))
        pale = ((lum > 125) & (chroma < 90)) | ((chroma < 30) & (lum > 48) & (lum < 185))
        pale_u8 = pale.astype(np.uint8) * 255
        fabric_u8 = is_fabric.astype(np.uint8) * 255
        seed = cv2.bitwise_and(cv2.dilate(fabric_u8, np.ones((5, 5), np.uint8), iterations=2), pale_u8)
        mask = seed
        kernel = np.ones((3, 3), np.uint8)
        for _ in range(48):
            nxt = cv2.bitwise_and(cv2.dilate(mask, kernel, iterations=1), pale_u8)
            if int(cv2.countNonZero(cv2.subtract(nxt, mask))) == 0:
                break
            mask = nxt
        if int(mask.max()) == 0:
            return
        mask = cv2.dilate(mask, kernel, iterations=1)
        fabric_px = rgb[(is_fabric) & (mask == 0)]
        local = (
            np.median(fabric_px, axis=0).astype(np.uint8)
            if len(fabric_px)
            else np.array(fabric, dtype=np.uint8)
        )
        if fill:
            rgb[mask > 0] = local
            lum2 = rgb.mean(axis=2)
            chroma2 = rgb.max(axis=2) - rgb.min(axis=2)
            on_product = cv2.blur(lum.astype(np.float32), (25, 25)) < 165
            leftover = (lum2 > 140) & (chroma2 < 70) & on_product
            if leftover.any():
                rgb[leftover] = local
        else:
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            filled = cv2.inpaint(bgr, mask, 5, cv2.INPAINT_TELEA)
            rgb = cv2.cvtColor(filled, cv2.COLOR_BGR2RGB)
        crop[:, :, :3] = rgb
        page.paste(PILImage.fromarray(crop), (x0, y0))

    def _fill_cover(
        self,
        page: PILImage.Image,
        cover: tuple[float, float, float, float],
        fabric: tuple[int, int, int],
    ) -> None:
        """Paint out the original mark with a solid fabric patch, then one logo goes on top."""
        x, y, w, h = _pts(cover)
        draw = ImageDraw.Draw(page)
        draw.rectangle((x, y, x + w, y + h), fill=fabric + (255,))

    def _blank_photo_logo_zone(
        self,
        page: PILImage.Image,
        cover: tuple[float, float, float, float],
        fabric: tuple[int, int, int],
    ) -> None:
        """Wipe baked sample marks on the Black front photo using local fabric color.

        ``backpack_front_base.png`` still contains the M13 sample; pale inpaint alone
        leaves ghosts. Fill the logo cover with the median dark-fabric rim color so
        only the client mark is stamped afterward.
        """
        import cv2
        import numpy as np

        x, y, w, h = _pts(cover)
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(page.width, x + w), min(page.height, y + h)
        if x1 - x0 < 12 or y1 - y0 < 12:
            return
        crop = np.array(page.crop((x0, y0, x1, y1)).convert("RGB"))
        hh, ww = crop.shape[:2]
        lum = crop.mean(axis=2).astype(np.float32)
        chroma = crop.max(axis=2) - crop.min(axis=2)
        # Pale / near-white sample glyphs on black fabric.
        pale = ((lum > 95) & (chroma < 55)) | ((lum > 140) & (chroma < 80))
        mask = pale.astype(np.uint8) * 255
        if int(mask.max()) == 0:
            # Fallback: blank whole cover with dark rim fabric.
            band = max(4, min(hh, ww) // 12)
            rim = np.zeros((hh, ww), dtype=bool)
            rim[:band, :] = True
            rim[-band:, :] = True
            rim[:, :band] = True
            rim[:, -band:] = True
            dark = rim & (lum < 90)
            local = (
                np.median(crop[dark], axis=0).astype(np.uint8)
                if int(dark.sum()) >= 16
                else np.array(fabric, dtype=np.uint8)
            )
            crop[:, :] = local
            page.paste(PILImage.fromarray(crop), (x0, y0))
            return

        mask = cv2.dilate(mask, np.ones((7, 7), np.uint8), iterations=3)
        # Heal with surrounding fabric so the plate does not read as a flat patch.
        bgr = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)
        healed = cv2.inpaint(bgr, mask, 7, cv2.INPAINT_TELEA)
        crop = cv2.cvtColor(healed, cv2.COLOR_BGR2RGB)
        # Second pass: any leftover pale crumbs → local dark fabric.
        lum2 = crop.mean(axis=2)
        chroma2 = crop.max(axis=2) - crop.min(axis=2)
        leftover = (lum2 > 110) & (chroma2 < 60)
        if leftover.any():
            dark_px = crop[(lum2 < 85) & (~leftover)]
            local = (
                np.median(dark_px, axis=0).astype(np.uint8)
                if len(dark_px) >= 16
                else np.array(fabric, dtype=np.uint8)
            )
            crop[leftover] = local
        page.paste(PILImage.fromarray(crop), (x0, y0))

    def _clear_lineart_logo_zone(
        self,
        page: PILImage.Image,
        cover: tuple[float, float, float, float],
        fabric: tuple[int, int, int],
        box: tuple[float, float, float, float] | None = None,
    ) -> None:
        """Remove the baked sample mark on Graphic Sample Option #1 line art.

        Flat line-art fill already paints the bag to fabric RGB, so filling the
        9.2 × 4.5 cm bound with the same fabric is continuous (no plate). Any
        remaining bright/white glyph pixels from the sample mark are healed
        cleanly without contaminating surrounding ink lines or zipper pulls.
        """
        import cv2
        import numpy as np

        x, y, w, h = _pts(cover)
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(page.width, x + w), min(page.height, y + h)
        if x1 - x0 < 12 or y1 - y0 < 12:
            return
        crop = np.array(page.crop((x0, y0, x1, y1)).convert("RGB"))
        fabric_lum = float(np.mean(fabric))
        lum = crop.mean(axis=2).astype(np.float32)

        # Only target bright glyph pixels significantly brighter than fabric background
        pale = lum > max(185.0, fabric_lum + 40.0)
        mask = (pale.astype(np.uint8) * 255)
        if int(mask.max()) > 0:
            mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=1)
            bgr = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)
            healed = cv2.inpaint(bgr, mask, 3, cv2.INPAINT_TELEA)
            crop = cv2.cvtColor(healed, cv2.COLOR_BGR2RGB)
            page.paste(PILImage.fromarray(crop), (x0, y0))

        art_box = box or cover
        self._fill_cover(page, art_box, fabric)

    def _paint_artwork_swatch(
        self,
        page: PILImage.Image,
        template: PILImage.Image,
        slot: dict,
        fabric: tuple[int, int, int],
    ) -> None:
        """Artwork callout: neutral background (#F4F4F5) so dark artwork remains clear regardless of fabric selection."""
        cover = slot.get("cover") or slot.get("box")
        if not cover:
            return
        x, y, w, h = _pts(cover)
        if w < 1 or h < 1:
            return
        swatch = self.renderer.solid_artwork_panel((w, h), bg_rgb=(244, 244, 245), border_rgb=(226, 232, 240))
        if page.mode == "RGBA":
            page.paste(swatch, (x, y), swatch)
        else:
            page.paste(swatch.convert("RGB"), (x, y))

    def _clear_schematic_fill(
        self,
        page: PILImage.Image,
        cover: tuple[float, float, float, float],
        fill: tuple[int, int, int] = (255, 255, 255),
    ) -> None:
        """Recolor the top-view company-logo gore (gray placeholder) to a contrast fill."""
        import cv2
        import numpy as np

        x, y, w, h = _pts(cover)
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(page.width, x + w), min(page.height, y + h)
        if x1 - x0 < 8 or y1 - y0 < 8:
            return
        crop = np.array(page.crop((x0, y0, x1, y1)))
        rgb = crop[:, :, :3]
        lum = rgb.mean(axis=2)
        chroma = rgb.max(axis=2) - rgb.min(axis=2)
        placeholder = (chroma < 42) & (lum < 242)
        blob = cv2.erode(placeholder.astype(np.uint8) * 255, np.ones((3, 3), np.uint8), iterations=1)
        blob = cv2.dilate(blob, np.ones((5, 5), np.uint8), iterations=3)
        rgb[blob > 0] = np.array(fill, dtype=np.uint8)
        crop[:, :, :3] = rgb
        page.paste(PILImage.fromarray(crop), (x0, y0))

    def _stamp_colors(self, page: PILImage.Image, spec: dict, job: JobSpec) -> None:
        colors = spec.get("colors")
        if not colors:
            return
        draw = ImageDraw.Draw(page)
        fabric = job.fabric_rgb
        logo_rgb = logo_color_rgb(job.logo_color_name)
        outline = (35, 35, 35, 255)
        stroke = max(1, int(round(SCALE)))

        sx, sy, sw, sh = _pts(colors["fabric_swatch"])
        draw.rectangle((sx, sy, sx + sw, sy + sh), fill=fabric + (255,))
        if max(fabric) > 210:
            draw.rectangle((sx, sy, sx + sw, sy + sh), outline=outline, width=stroke)

        lx, ly, lw, lh = _pts(colors["logo_swatch"])
        draw.rectangle((lx, ly, lx + lw, ly + lh), fill=logo_rgb + (255,))
        if max(logo_rgb) > 210:
            draw.rectangle((lx, ly, lx + lw, ly + lh), outline=outline, width=stroke)

        font = _font(False, int(colors.get("font_pt", 14) * SCALE))
        self._stamp_label(draw, colors["fabric_label"], fabric_sheet_lines(job.fabric_name), font)
        self._stamp_label(draw, colors["logo_label"], [job.logo_color_name], font)

    def _stamp_label(
        self,
        draw: ImageDraw.ImageDraw,
        box: tuple[float, float, float, float],
        lines: list[str],
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    ) -> None:
        x, y, w, h = _pts(box)
        draw.rectangle((x, y, x + w, y + h), fill=(255, 255, 255, 255))
        lines = [ln for ln in lines if ln]
        if not lines:
            return
        gap = max(2, int(2 * SCALE))
        sizes = [draw.textbbox((0, 0), ln, font=font) for ln in lines]
        heights = [b[3] - b[1] for b in sizes]
        total = sum(heights) + gap * (len(lines) - 1)
        cy = y + max(0, (h - total) // 2)
        fill = NAVY + (255,)
        for ln, bh in zip(lines, heights):
            draw.text((x, cy), ln, font=font, fill=fill)
            cy += bh + gap

    def _stamp_header(self, page: PILImage.Image, spec: dict, job: JobSpec) -> None:
        draw = ImageDraw.Draw(page)
        fields = spec.get("header_fields") or {}
        if fields:
            font_meta = _font(False, int(16 * SCALE))
            values = {
                "request_date": job.request_date or "—",
                "last_update": job.last_update or "—",
                "project_owner": job.project_owner or "—",
                "print_order": job.print_order or "—",
            }
            for key, box in fields.items():
                text = str(values.get(key) or "—")
                if text in {"", "—"} and key == "print_order":
                    text = "—"
                x, y, w, h = _pts(box)
                draw.rectangle((x, y, x + w, y + h), fill=(255, 255, 255, 255))
                draw.text((x, y + h * 0.5), text, font=font_meta, fill=NAVY + (255,), anchor="lm")

        chip_box = spec.get("chip")
        if chip_box:
            cx, cy, cw, ch = _pts(chip_box)
            # Fill with header background to remove any dark navy chip block completely
            draw.rectangle((cx - 2, cy - 2, cx + cw + 2, cy + ch + 2), fill=HEADER_BG + (255,))

    def _recolor_fabric(
        self,
        page: PILImage.Image,
        fabric: tuple[int, int, int],
        regions: list[tuple[float, float, float, float]] | None = None,
        polygons: list[list[tuple[float, float]]] | None = None,
        max_lum: float = 95,
    ) -> PILImage.Image:
        """Shift near-black fabric pixels toward the selected color.

        Optional ``regions`` (axis-aligned) and ``polygons`` (PDF-point silhouettes)
        limit which pixels may change — used so backpack photo recolor cannot
        spill onto the model's coat, and line-art fills cover the full bag body.
        """
        import cv2
        import numpy as np

        arr = np.array(page.convert("RGBA"))
        rgb = arr[:, :, :3].astype("int16")
        lum = rgb.max(axis=2)
        chroma = rgb.max(axis=2) - rgb.min(axis=2)
        # Include soft canopy shading so light fabrics do not leave charcoal patches.
        # Backpack specs raise max_lum so handle/side midtones tint with the body.
        mask = (lum < max_lum) & (chroma < 42)
        if regions or polygons:
            allowed = np.zeros(mask.shape, dtype=bool)
            for box in regions or []:
                x, y, w, h = _pts(box)
                y1, x1 = min(mask.shape[0], y + h), min(mask.shape[1], x + w)
                allowed[max(0, y) : y1, max(0, x) : x1] = True
            if polygons:
                poly_layer = np.zeros(mask.shape, dtype=np.uint8)
                for poly in polygons:
                    if len(poly) < 3:
                        continue
                    pts = np.array([_pt_xy(float(px), float(py)) for px, py in poly], dtype=np.int32)
                    cv2.fillPoly(poly_layer, [pts], 1)
                # Pull 2px off the silhouette edge so coat fringe never picks up fabric tint.
                poly_layer = cv2.erode(poly_layer, np.ones((5, 5), np.uint8), iterations=1)
                allowed |= poly_layer.astype(bool)
            mask &= allowed
            # Drop olive/coat-like pixels that still fall inside the silhouette.
            if polygons:
                poly_only = poly_layer.astype(bool)
                g_dom = rgb[:, :, 1].astype("int16") - np.maximum(rgb[:, :, 0], rgb[:, :, 2]).astype("int16")
                fringe = poly_only & ((chroma >= 26) | (g_dom > 8))
                mask &= ~fringe
        if not mask.any():
            return page
        src = np.array(FABRIC_COLORS.get("Black (NRF 001)", (30, 30, 30)), dtype="int16")
        dst = np.array(fabric, dtype="int16")
        delta = dst - src
        work = rgb
        if regions:
            # Flat-art fills are often pure black (0,0,0), darker than NRF Black.
            # Lift those inside rectangular regions so handles/mesh match the body.
            # Photo polygons keep natural shading (no lift).
            region_only = np.zeros(mask.shape, dtype=bool)
            for box in regions:
                x, y, w, h = _pts(box)
                y1, x1 = min(mask.shape[0], y + h), min(mask.shape[1], x + w)
                region_only[max(0, y) : y1, max(0, x) : x1] = True
            lifted = np.maximum(rgb, src)
            work = np.where(region_only[..., None], lifted, rgb)
        for i in range(3):
            channel = work[:, :, i] + mask * delta[i]
            arr[:, :, i] = np.clip(channel, 0, 255).astype("uint8")
        return PILImage.fromarray(arr)

    def _draw_full_page(
        self,
        c: canvas.Canvas,
        image: PILImage.Image,
        size_pts: tuple[float, float],
    ) -> None:
        buf = BytesIO()
        image.convert("RGB").save(buf, format="JPEG", quality=92, optimize=True)
        buf.seek(0)
        c.drawImage(ImageReader(buf), 0, 0, width=size_pts[0], height=size_pts[1])
