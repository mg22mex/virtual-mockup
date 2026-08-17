"""Production worksheets built from the official Illustrator PDF.

The Proper Brands x WM Umbrella 2026 sheet is the page template. This module
covers the original Proper marks, stamps the current job logo, and rewrites
header fields. Layout, photography, callouts, and pagination stay untouched.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .catalog import fabric_sheet_lines, logo_color_rgb
from .renderer import (
    FABRIC_COLORS,
    NAVY,
    JobSpec,
    MockupRenderer,
)

ROOT = Path(__file__).resolve().parent.parent
OFFICIAL_PDF = ROOT / "assets" / "templates" / "official_worksheet.pdf"
OFFICIAL_PAGES = ROOT / "assets" / "templates" / "official"
TEMPLATE_DPI = 144
SCALE = TEMPLATE_DPI / 72.0  # template pixels per PDF point

_FONT_DIR = Path("/usr/share/fonts/liberation")

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
}

PAGE_TITLES: dict[int, str] = {
    1: "Walk",
    2: "Golf Essential",
    3: "Graphic sizing",
    4: "Sleeve",
}

# Coordinates are PDF points at 72 dpi (page-1 = 2126×3260, golf = 2126×3544).
# `box` is the fitted logo; `cover` is inpainted so original ink leaves no patch.
PAGE_SPEC: dict[int, dict] = {
    1: {
        "size_pts": (2125.98, 3259.84),
        "logos": [
            # Front canopy: photo-inpaint so official white Proper is fully gone (ink left a ghost).
            {"box": (485, 860, 176, 42), "cover": (455, 835, 240, 95), "erase": "photo"},
            # Closed-sleeve Weatherman wordmark under Front View → customer logo.
            {"box": (670, 1410, 170, 24), "cover": (640, 1394, 270, 56), "erase": "block"},
            {"box": (758, 2504, 610, 165), "cover": (742, 2488, 644, 200), "erase": "block"},
        ],
        "chip": (1300, 50, 618, 168),
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
            {"box": (1248, 3198, 210, 44), "cover": (1228, 3188, 248, 64), "erase": "ink"},
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


def worksheet_filename(client: str, year: int | None = None) -> str:
    year = year or date.today().year
    safe = " ".join(client.strip().split()) or "Client"
    return f"{safe} x WM Umbrella {year} Mockup Designs.pdf"


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


def _recolor_ink(mark: PILImage.Image, rgb: tuple[int, int, int]) -> PILImage.Image:
    import numpy as np

    arr = np.array(mark.convert("RGBA"))
    arr[:, :, 0] = int(rgb[0])
    arr[:, :, 1] = int(rgb[1])
    arr[:, :, 2] = int(rgb[2])
    return PILImage.fromarray(arr)


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
        self._pages: dict[int, PILImage.Image] = {}

    def _template(self, page_no: int) -> PILImage.Image:
        if page_no not in self._pages:
            path = OFFICIAL_PAGES / f"page-{page_no}.png"
            if not path.exists():
                raise FileNotFoundError(
                    f"Official worksheet page missing: {path}. "
                    "Place the Illustrator PDF at assets/templates/official_worksheet.pdf "
                    f"and rasterize with: pdftoppm -png -r {TEMPLATE_DPI} ..."
                )
            self._pages[page_no] = PILImage.open(path).convert("RGBA")
        return self._pages[page_no].copy()

    def page_plan(self, job: JobSpec) -> list[tuple[int, str]]:
        """Official worksheet pages that will be included for the selected styles."""
        seen: set[int] = set()
        plan: list[tuple[int, str]] = []
        for key in job.product_keys:
            for page_no in STYLE_PAGES.get(key, []):
                if page_no in seen:
                    continue
                seen.add(page_no)
                plan.append((page_no, PAGE_TITLES.get(page_no, f"Page {page_no}")))
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
        seen: set[int] = set()
        for key in job.product_keys:
            for page_no in STYLE_PAGES.get(key, []):
                if page_no in seen:
                    continue
                seen.add(page_no)
                yield page_no, PAGE_TITLES.get(page_no, f"Page {page_no}"), self._compose_page(
                    page_no, job, mark
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
        return previews

    def build_pdf(self, job: JobSpec, logo: PILImage.Image | None) -> bytes:
        buffer = BytesIO()
        first_pages = STYLE_PAGES.get(job.product_keys[0], [1]) if job.product_keys else [1]
        w, h = PAGE_SPEC[first_pages[0]]["size_pts"]
        c = canvas.Canvas(buffer, pagesize=(w, h))
        c.setTitle(worksheet_filename(job.client, job.year).replace(".pdf", ""))
        c.setAuthor("Weatherman Virtual Mockup Creator")
        c.setSubject("PRODUCTION WORKSHEET")

        for page_no, _title, page in self.iter_job_pages(job, logo):
            spec = PAGE_SPEC[page_no]
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
    ) -> PILImage.Image:
        page = self._template(page_no)
        spec = PAGE_SPEC[page_no]
        fabric = job.fabric_rgb
        black = FABRIC_COLORS.get("Black (NRF 001)", (35, 35, 35))
        # Always clear official Proper / Weatherman marks first so nothing is
        # preloaded. Client art is stamped only after an upload provides `mark`.
        for slot in spec["logos"]:
            self._erase_slot(page, slot, black)
        if fabric != black:
            page = self._recolor_fabric(page, fabric)
        if mark is not None:
            for slot in spec["logos"]:
                self._stamp_logo(page, slot, mark, fabric, erase=False)
        self._stamp_colors(page, spec, job)
        self._stamp_header(page, spec, job)
        return page

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
        elif erase == "ink":
            self._erase_pale_on_fabric(page, cover, fabric, fill=False)
        elif erase == "flat":
            self._erase_pale_on_fabric(page, cover, fabric, fill=True)
        elif erase == "block":
            self._fill_cover(page, cover, fabric)
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
        _ = fabric

        x, y, w, h = _pts(slot["box"])
        rotate = int(slot.get("rotate") or 0)
        art = _trim_mark(mark.convert("RGBA"))
        ink = slot.get("ink")
        if ink:
            art = _recolor_ink(art, tuple(int(v) for v in ink))
        if rotate:
            art = art.rotate(rotate, expand=True, resample=PILImage.Resampling.BICUBIC)
        if art.width < 1 or art.height < 1:
            return
        outline = slot.get("outline")
        outline_px = max(1, int(round(float(slot.get("outline_pt") or 0) * SCALE))) if outline else 0
        fit_w = max(1, w - outline_px * 2)
        fit_h = max(1, h - outline_px * 2)
        scale = min(fit_w / art.width, fit_h / art.height)
        nw, nh = max(1, int(art.width * scale)), max(1, int(art.height * scale))
        art = art.resize((nw, nh), PILImage.Resampling.LANCZOS)
        if outline:
            art = _outline_mark(
                art,
                tuple(int(v) for v in outline),
                outline_px,
                fill=not bool(slot.get("outline_only")),
            )
        px = x + (w - art.width) // 2
        py = y + (h - art.height) // 2
        page.paste(art, (px, py), art)

    def _inpaint_cover(self, page: PILImage.Image, cover: tuple[float, float, float, float]) -> None:
        """Rebuild fabric through a slot so original marks leave no flat patch."""
        import cv2
        import numpy as np

        x, y, w, h = _pts(cover)
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(page.width, x + w), min(page.height, y + h)
        if x1 - x0 < 12 or y1 - y0 < 12:
            return
        crop = np.array(page.crop((x0, y0, x1, y1)))
        rgb = crop[:, :, :3]
        lum = rgb.mean(axis=2)
        mask = np.zeros((crop.shape[0], crop.shape[1]), np.uint8)
        border = max(4, min(crop.shape[0], crop.shape[1]) // 14)
        mask[border : crop.shape[0] - border, border : crop.shape[1] - border] = 255
        # Keep worksheet paper; still erase pale ink sitting on fabric.
        paper = cv2.blur(lum.astype(np.float32), (31, 31)) > 220
        mask[paper & (lum > 230)] = 0
        if int(mask.max()) == 0:
            return
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        filled = cv2.inpaint(bgr, mask, 6, cv2.INPAINT_TELEA)
        rgb2 = cv2.cvtColor(filled, cv2.COLOR_BGR2RGB)
        lum2 = rgb2.mean(axis=2)
        chroma2 = rgb2.max(axis=2) - rgb2.min(axis=2)
        leftover = (lum2 > 168) & (chroma2 < 42) & (~paper)
        if leftover.any():
            fabric_px = rgb2[(lum2 < 140) & (~leftover)]
            if len(fabric_px):
                rgb2[leftover] = np.median(fabric_px, axis=0)
        crop[:, :, :3] = rgb2
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
        cx, cy, cw, ch = _pts(spec["chip"])
        draw.rounded_rectangle((cx, cy, cx + cw, cy + ch), radius=int(6 * SCALE), fill=NAVY + (255,))
        label = job.client.strip() or "Client"
        config = job.panel_config or "Standard 1 Panel"
        font_a = _font(True, int(22 * SCALE))
        font_b = _font(False, int(18 * SCALE))
        draw.text((cx + cw / 2, cy + ch * 0.34), label, font=font_a, fill=(255, 255, 255, 255), anchor="mm")
        draw.text((cx + cw / 2, cy + ch * 0.66), f"({config})", font=font_b, fill=(255, 255, 255, 255), anchor="mm")

    def _recolor_fabric(self, page: PILImage.Image, fabric: tuple[int, int, int]) -> PILImage.Image:
        """Shift near-black canopy/sleeve pixels toward the selected fabric."""
        import numpy as np

        arr = np.array(page.convert("RGBA"))
        rgb = arr[:, :, :3].astype("int16")
        lum = rgb.max(axis=2)
        chroma = rgb.max(axis=2) - rgb.min(axis=2)
        # Include soft canopy shading so light fabrics do not leave charcoal patches.
        mask = (lum < 95) & (chroma < 36)
        if not mask.any():
            return page
        src = np.array(FABRIC_COLORS.get("Black (NRF 001)", (35, 35, 35)), dtype="int16")
        dst = np.array(fabric, dtype="int16")
        delta = dst - src
        for i in range(3):
            channel = rgb[:, :, i] + mask * delta[i]
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
