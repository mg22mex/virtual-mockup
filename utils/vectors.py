"""Rasterize client artwork from vector formats (SVG, AI, CDR, EPS, PDF).

Uses system tools already on the workstation / Streamlit Cloud packages.txt:
  SVG  → rsvg-convert (librsvg)
  AI/EPS/PDF → Ghostscript / pdftocairo / ImageMagick
  CDR  → ImageMagick, then ZIP-preview fallback for Corel X4+ packages
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


def _open_png_bytes(data: bytes) -> Image.Image:
    image = Image.open(BytesIO(data))
    image.load()
    return image.convert("RGBA")


def _rasterize_svg(raw: bytes, width_px: int) -> Image.Image:
    rsvg = _which("rsvg-convert")
    if not rsvg:
        raise VectorLoadError("SVG support requires rsvg-convert (librsvg).")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "art.svg"
        dst = Path(tmp) / "art.png"
        src.write_bytes(raw)
        result = _run([rsvg, "-u", "-w", str(width_px), "-f", "png", "-o", str(dst), str(src)])
        if result.returncode != 0 or not dst.exists():
            magick = _which("magick", "convert")
            if not magick:
                err = (result.stderr or result.stdout or b"").decode("utf-8", "ignore")[:400]
                raise VectorLoadError(f"Could not rasterize SVG. {err}")
            result = _run([magick, "-background", "none", "-density", "300", str(src), str(dst)])
            if result.returncode != 0 or not dst.exists():
                raise VectorLoadError("Could not rasterize SVG with rsvg-convert or ImageMagick.")
        return Image.open(dst).convert("RGBA")


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
            f"Could not rasterize {suffix} artwork. Ghostscript/pdftocairo/ImageMagick failed."
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
        "Could not rasterize CorelDRAW (.cdr). Export the logo to SVG or PDF, "
        "or install ImageMagick with CDR support."
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
