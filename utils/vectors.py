"""Rasterize client artwork from vector formats (SVG, AI, CDR, EPS, PDF).

Primary path is pure-Python PyMuPDF (no apt packages on Streamlit Cloud).
Optional system tools (rsvg, Ghostscript, Poppler, ImageMagick) are used
only when present — local workstations can keep them; Cloud boots without them.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

from PIL import Image

VECTOR_EXTS = {".svg", ".ai", ".cdr", ".eps", ".pdf"}
SUPPORTED_EXTS = sorted(VECTOR_EXTS)


class VectorLoadError(ValueError):
    """Artwork could not be parsed or rasterized."""


def _which(*names: str) -> str | None:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def _run(cmd: list[str], timeout: int = 45) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(cmd, check=False, capture_output=True, timeout=timeout)


def _pixmap_to_image(pix) -> Image.Image:
    mode = "RGBA" if pix.alpha else "RGB"
    image = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    return image.convert("RGBA")


def _fitz_raster(raw: bytes, filetype: str, *, dpi: int = 300, width_px: int | None = None) -> Image.Image | None:
    """Render with PyMuPDF when the bytes are a supported document type."""
    try:
        import fitz
    except ImportError:
        return None
    try:
        doc = fitz.open(stream=raw, filetype=filetype)
    except Exception:
        return None
    try:
        if doc.page_count < 1:
            return None
        page = doc[0]
        if width_px and page.rect.width > 0:
            zoom = width_px / float(page.rect.width)
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=True)
        else:
            pix = page.get_pixmap(dpi=dpi, alpha=True)
        if pix.width < 2 or pix.height < 2:
            return None
        return _pixmap_to_image(pix)
    except Exception:
        return None
    finally:
        doc.close()


def _rasterize_svg(raw: bytes, width_px: int) -> Image.Image:
    # Prefer librsvg when present — it honors embedded/system fonts and kerning.
    # PyMuPDF is a solid fallback on Streamlit Cloud but may substitute fonts.
    rsvg = _which("rsvg-convert")
    if rsvg:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "art.svg"
            dst = Path(tmp) / "art.png"
            src.write_bytes(raw)
            result = _run([rsvg, "-u", "-w", str(width_px), "-f", "png", "-o", str(dst), str(src)])
            if result.returncode == 0 and dst.exists():
                return Image.open(dst).convert("RGBA")

    image = _fitz_raster(raw, "svg", width_px=width_px)
    if image is not None:
        return image

    raise VectorLoadError(
        "Could not rasterize SVG. Install PyMuPDF (pip) or rsvg-convert (librsvg)."
    )


def _ghostscript_png(src: Path, dst: Path, dpi: int) -> bool:
    gs = _which("gs")
    if not gs:
        return False
    result = _run(
        [
            gs,
            "-dSAFER",
            "-dBATCH",
            "-dNOPAUSE",
            "-dQUIET",
            "-sDEVICE=pngalpha",
            f"-r{dpi}",
            "-dFirstPage=1",
            "-dLastPage=1",
            f"-sOutputFile={dst}",
            str(src),
        ]
    )
    return result.returncode == 0 and dst.exists() and dst.stat().st_size > 0


def _pdftocairo_png(src: Path, dst_prefix: Path, dpi: int) -> Path | None:
    tool = _which("pdftocairo")
    if not tool:
        return None
    result = _run([tool, "-png", "-r", str(dpi), "-f", "1", "-l", "1", "-singlefile", str(src), str(dst_prefix)])
    out = Path(str(dst_prefix) + ".png")
    if result.returncode == 0 and out.exists():
        return out
    return None


def _imagemagick_png(src: Path, dst: Path, dpi: int) -> bool:
    magick = _which("magick", "convert")
    if not magick:
        return False
    result = _run(
        [magick, "-background", "none", "-density", str(dpi), f"{src}[0]", str(dst)],
        timeout=60,
    )
    return result.returncode == 0 and dst.exists() and dst.stat().st_size > 0


def _rasterize_pdf_family(raw: bytes, suffix: str, dpi: int) -> Image.Image:
    # Many .ai files are PDF-compatible; try PDF first for both.
    for filetype in ("pdf", "svg") if suffix == ".pdf" else ("pdf",):
        image = _fitz_raster(raw, filetype, dpi=dpi)
        if image is not None:
            return image
    if suffix == ".ai":
        image = _fitz_raster(raw, "pdf", dpi=dpi)
        if image is not None:
            return image

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"art{suffix}"
        dst = Path(tmp) / "art.png"
        src.write_bytes(raw)
        if suffix in {".pdf", ".ai", ".eps"} and _ghostscript_png(src, dst, dpi):
            return Image.open(dst).convert("RGBA")
        cairo_out = _pdftocairo_png(src, Path(tmp) / "page", dpi) if suffix in {".pdf", ".ai"} else None
        if cairo_out is not None:
            return Image.open(cairo_out).convert("RGBA")
        if _imagemagick_png(src, dst, dpi):
            return Image.open(dst).convert("RGBA")
    raise VectorLoadError(
        f"Could not rasterize {suffix} artwork. Need PyMuPDF, or Ghostscript/Poppler locally."
    )


def _cdr_preview_from_zip(raw: bytes) -> Image.Image | None:
    """Newer CorelDRAW packages are ZIP containers with a preview bitmap."""
    if raw[:2] != b"PK":
        return None
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            names = archive.namelist()
            candidates = [
                name
                for name in names
                if name.lower().endswith((".png", ".bmp", ".jpg", ".jpeg", ".tif", ".wmf", ".emf"))
                or "preview" in name.lower()
                or "thumbnail" in name.lower()
            ]
            for name in candidates or names:
                try:
                    data = archive.read(name)
                    return Image.open(BytesIO(data)).convert("RGBA")
                except Exception:
                    continue
    except zipfile.BadZipFile:
        return None
    return None


def _rasterize_cdr(raw: bytes, dpi: int) -> Image.Image:
    preview = _cdr_preview_from_zip(raw)
    if preview is not None:
        return preview
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "art.cdr"
        dst = Path(tmp) / "art.png"
        src.write_bytes(raw)
        if _imagemagick_png(src, dst, dpi):
            return Image.open(dst).convert("RGBA")
    raise VectorLoadError(
        "Could not rasterize CorelDRAW (.cdr). Export the logo to SVG or PDF "
        "(ZIP-based CDR previews work without ImageMagick)."
    )


def load_artwork(
    raw: bytes,
    filename: str,
    *,
    target_width: int = 2400,
    dpi: int = 300,
) -> Image.Image:
    """Return an RGBA raster of uploaded client artwork."""
    suffix = Path(filename).suffix.lower() or ".bin"
    if suffix not in VECTOR_EXTS:
        raise VectorLoadError(
            f"Unsupported artwork format: {suffix}. "
            "Upload SVG, AI, CDR, PDF, or EPS."
        )

    if suffix == ".svg":
        return _rasterize_svg(raw, target_width)
    if suffix == ".cdr":
        return _rasterize_cdr(raw, dpi)
    if suffix in {".ai", ".eps", ".pdf"}:
        return _rasterize_pdf_family(raw, suffix, dpi)
    raise VectorLoadError(f"Unsupported artwork format: {suffix}")
