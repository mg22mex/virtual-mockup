"""Weatherman Virtual Mockup Creator — Streamlit dashboard.

UI stays decoupled from rendering and PDF export (utils/).
Live proof shows the official production-worksheet pages after stamping.

Module import is side-effect free: only imports + defs at top level.
Streamlit cache registration and utils imports run inside main().
"""

from __future__ import annotations

import hashlib
import traceback
from datetime import date
from pathlib import Path
from typing import Any, Callable

import streamlit as st

# Top-level scope: imports + constants + function definitions only.
ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
LOGO_DIR = ROOT / "assets" / "logos"
WM_MARK = ROOT / "assets" / "templates" / "wm_mark.png"
PANEL_OPTIONS = [
    "Standard 1 Panel",
    "Standard 2 Panel",
    "Standard 4 Panel",
    "All-over 8 Panel",
]

STAMP_VERSION = 54
# Widget key namespace — bump to force a blank ticket on existing Cloud sessions.
FORM_KEY = "blank2"
FAMILY_OPTIONS = ["Umbrella", "Backpack", "Poncho"]
FAMILY_KEYS = {"Umbrella": "umbrella", "Backpack": "backpack", "Poncho": "poncho"}

# Filled by _ensure_imports() on first main() entry — never at import time.
_IMPORT_ERROR: str | None = None
_IMPORTS_READY = False
AssetLogger: Any = None
StateMemory: Any = None
WorksheetExporter: Any = None
JobSpec: Any = None
VectorLoadError: Any = Exception
worksheet_filename: Any = None
fabric_caption: Any = None
fabrics_for_styles: Any = None
logo_color_names: Any = None
logo_knockout_mode: Any = None
style_labels: Any = None
render_project_guide: Any = None
load_artwork: Any = None
SUPPORTED_EXTS: set[str] = {".svg"}

_init_cached: Callable[..., Any] | None = None
_preview_pages_cached: Callable[..., Any] | None = None


def _ensure_imports() -> str | None:
    """Import app dependencies once inside main() (never at module import)."""
    global _IMPORT_ERROR, _IMPORTS_READY
    global AssetLogger, StateMemory, WorksheetExporter, JobSpec, VectorLoadError
    global worksheet_filename, fabric_caption, fabrics_for_styles, logo_color_names
    global logo_knockout_mode, style_labels, render_project_guide, load_artwork, SUPPORTED_EXTS
    if _IMPORTS_READY:
        return _IMPORT_ERROR
    try:
        from skills.asset_logger import AssetLogger as _AssetLogger
        from skills.state_memory import StateMemory as _StateMemory
        from utils.catalog import (
            fabric_caption as _fabric_caption,
            fabrics_for_styles as _fabrics_for_styles,
            logo_color_names as _logo_color_names,
            logo_knockout_mode as _logo_knockout_mode,
            style_labels as _style_labels,
        )
        from utils.exporter import WorksheetExporter as _WorksheetExporter
        from utils.exporter import worksheet_filename as _worksheet_filename
        from utils.project_guide import render_project_guide as _render_project_guide
        from utils.renderer import JobSpec as _JobSpec
        from utils.vectors import SUPPORTED_EXTS as _SUPPORTED_EXTS
        from utils.vectors import VectorLoadError as _VectorLoadError
        from utils.vectors import load_artwork as _load_artwork

        AssetLogger = _AssetLogger
        StateMemory = _StateMemory
        WorksheetExporter = _WorksheetExporter
        JobSpec = _JobSpec
        VectorLoadError = _VectorLoadError
        worksheet_filename = _worksheet_filename
        fabric_caption = _fabric_caption
        fabrics_for_styles = _fabrics_for_styles
        logo_color_names = _logo_color_names
        logo_knockout_mode = _logo_knockout_mode
        style_labels = _style_labels
        render_project_guide = _render_project_guide
        load_artwork = _load_artwork
        SUPPORTED_EXTS = set(_SUPPORTED_EXTS)
        _IMPORT_ERROR = None
    except Exception:  # noqa: BLE001 — show Cloud import crashes on-screen
        _IMPORT_ERROR = traceback.format_exc()
    _IMPORTS_READY = True
    return _IMPORT_ERROR


def _logo_fingerprint(logo_bytes: bytes | None, logo_name: str | None) -> str:
    """Stable content key so a new upload always invalidates the preview cache."""
    if not logo_bytes:
        return "none"
    digest = hashlib.sha1(logo_bytes).hexdigest()[:16]
    return f"{logo_name or 'logo'}:{len(logo_bytes)}:{digest}"


def _init_uncached(version: int = STAMP_VERSION) -> tuple[Any, Any, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    return StateMemory(ROOT), AssetLogger(ROOT), WorksheetExporter()


def _preview_pages_uncached(
    stamp_version: int,
    client: str,
    panel_config: str,
    panel_count: int,
    product_keys: tuple[str, ...],
    family: str,
    fabric_name: str,
    logo_color_name: str,
    request_date: str,
    last_update: str,
    project_owner: str,
    print_order: str,
    year: int,
    knockout_mode: str,
    knockout_white: bool,
    logo_fingerprint: str,
    logo_bytes: bytes | None,
    logo_name: str | None,
) -> list[tuple[str, bytes]]:
    _memory, _logger, exporter = _init(stamp_version)
    job = JobSpec(
        client=client,
        panel_config=panel_config,
        panel_count=panel_count,
        product_keys=list(product_keys),
        family=family,
        fabric_name=fabric_name,
        logo_color_name=logo_color_name,
        request_date=request_date,
        last_update=last_update,
        project_owner=project_owner,
        print_order=print_order,
        year=year,
        knockout_white=knockout_white,
    )
    job.knockout_mode = knockout_mode
    logo = load_artwork(logo_bytes, logo_name) if logo_bytes and logo_name else None
    return exporter.preview_jpegs(job, logo)


def _init(version: int = STAMP_VERSION) -> tuple[Any, Any, Any]:
    """Lazy ``st.cache_resource`` — registered only under a live Streamlit run."""
    global _init_cached
    if _init_cached is None:
        _init_cached = st.cache_resource(_init_uncached)
    return _init_cached(version)


def _preview_pages(
    stamp_version: int,
    client: str,
    panel_config: str,
    panel_count: int,
    product_keys: tuple[str, ...],
    family: str,
    fabric_name: str,
    logo_color_name: str,
    request_date: str,
    last_update: str,
    project_owner: str,
    print_order: str,
    year: int,
    knockout_mode: str,
    knockout_white: bool,
    logo_fingerprint: str,
    logo_bytes: bytes | None,
    logo_name: str | None,
) -> list[tuple[str, bytes]]:
    """Lazy ``st.cache_data`` — registered only under a live Streamlit run."""
    global _preview_pages_cached
    if _preview_pages_cached is None:
        # No show_spinner: Cloud reboots kill the spinner thread ("Event loop is closed").
        _preview_pages_cached = st.cache_data(max_entries=12)(_preview_pages_uncached)
    return _preview_pages_cached(
        stamp_version,
        client,
        panel_config,
        panel_count,
        product_keys,
        family,
        fabric_name,
        logo_color_name,
        request_date,
        last_update,
        project_owner,
        print_order,
        year,
        knockout_mode,
        knockout_white,
        logo_fingerprint,
        logo_bytes,
        logo_name,
    )


def _clear_preview_cache() -> None:
    try:
        if _preview_pages_cached is not None:
            _preview_pages_cached.clear()
    except Exception:
        pass


def _clear_artwork_state() -> None:
    for key in ("logo_bytes", "logo_name", "_saved_logo", "pdf_bytes", "pdf_name", "pdf_pages", "pdf_fingerprint"):
        st.session_state.pop(key, None)
    _clear_preview_cache()


def main() -> None:
    st.set_page_config(
        page_title="Virtual Mockup Creator · Weatherman",
        page_icon=":material/description:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    import_error = _ensure_imports()
    if import_error:
        print(import_error, flush=True)
        st.error("Failed to import application modules. Traceback is below.")
        st.code(import_error, language="text")
        return
    if WM_MARK.is_file():
        st.logo(str(WM_MARK), size="large")

    # Selected multiselect/segmented chips use theme.primaryColor (Weatherman coral).
    # Soften those to navy so they don't read as Streamlit validation errors.
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] span[data-baseweb="tag"] {
            background-color: #262D65 !important;
            color: #ffffff !important;
        }
        [data-testid="stSidebar"] span[data-baseweb="tag"] span,
        [data-testid="stSidebar"] span[data-baseweb="tag"] svg {
            color: #ffffff !important;
            fill: #ffffff !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    memory, logger, exporter = _init(STAMP_VERSION)

    st.caption("Internal tool · Sales and operations · Production proofs")
    st.title("Virtual mockup creator")
    st.caption("On-screen proof is the official Weatherman production worksheet with this job stamped on it.")

    with st.sidebar:
        st.subheader("Job ticket")
        client = st.text_input("Client", value="", placeholder="Client name", key=f"client_{FORM_KEY}") or ""
        owner = st.text_input("Project owner", value="", placeholder="Initials", key=f"owner_{FORM_KEY}") or ""
        print_order = st.text_input("Print order", value="", placeholder="Printer / PO", key=f"po_{FORM_KEY}") or ""
        request_date = st.text_input(
            "Request date",
            value="",
            placeholder="MM/DD/YYYY",
            key=f"req_{FORM_KEY}",
        ) or ""
        last_update = st.text_input(
            "Last update",
            value="",
            placeholder="MM/DD/YYYY",
            key=f"upd_{FORM_KEY}",
        ) or ""

        family_label = st.segmented_control(
            "Product family",
            FAMILY_OPTIONS,
            key=f"family_{FORM_KEY}",
        )
        family = FAMILY_KEYS.get(family_label or "")

        if family == "poncho":
            st.caption(
                "No production worksheet yet. Trail Hound Rain Vest is on Shopify "
                "(Bone / Navy / Sage). Add an official sheet to enable proofs."
            )
            labels = {}
            product_keys = []
            panel_config = None
            panel_count = 0
        else:
            labels = style_labels(family) if family else {}
            selected_labels = st.multiselect(
                "Products",
                options=list(labels.values()) if labels else [],
                default=[],
                placeholder="Choose styles" if family else "Choose a product family first",
                key=f"products_{FORM_KEY}_{family or 'none'}",
                disabled=not bool(labels),
            )
            label_to_key = {v: k for k, v in labels.items()}
            product_keys = [label_to_key[label] for label in selected_labels]

            if family == "backpack":
                panel_config = "Upper center"
                panel_count = 1
                st.caption("Artwork placement: upper center · 9.2 × 4.5 cm.")
            else:
                panel_config = st.selectbox(
                    "Panel configuration",
                    PANEL_OPTIONS,
                    index=None,
                    placeholder="Choose panel configuration",
                    key=f"panel_{FORM_KEY}",
                    disabled=family != "umbrella",
                )
                panel_count = {
                    "Standard 1 Panel": 1,
                    "Standard 2 Panel": 2,
                    "Standard 4 Panel": 4,
                    "All-over 8 Panel": 8,
                }.get(panel_config or "", 0)

        fabric_options = fabrics_for_styles(product_keys) if product_keys else []
        if fabric_options:
            fabric = st.selectbox(
                "Fabric / pattern color",
                fabric_options,
                index=None,
                placeholder="Choose fabric",
                format_func=fabric_caption,
                key=f"fabric_{FORM_KEY}",
            )
        else:
            st.selectbox(
                "Fabric / pattern color",
                ["—"],
                index=None,
                placeholder="Select products first",
                key=f"fabric_disabled_{FORM_KEY}",
                disabled=True,
            )
            fabric = None
        logo_options = logo_color_names()
        logo_color = st.selectbox(
            "Logo / graphic color",
            logo_options,
            index=None,
            placeholder="Choose logo color",
            key=f"logo_color_{FORM_KEY}",
        )
        knockout_mode = logo_knockout_mode(logo_color) if logo_color else "none"
        if logo_color and knockout_mode == "none":
            st.caption("Uploaded artwork colors are kept as-is.")
        elif logo_color:
            st.caption("Uploaded art is recolored to the selected print color.")
        year = st.number_input(
            "Worksheet year",
            min_value=2020,
            max_value=2040,
            value=None,
            step=1,
            format="%d",
            placeholder="Year",
            key=f"year_{FORM_KEY}",
        )
        if year is not None:
            year = int(year)

        ext_list = [e.lstrip(".") for e in SUPPORTED_EXTS]
        if "logo_uploader_id" not in st.session_state:
            st.session_state["logo_uploader_id"] = 0
        upload = st.file_uploader(
            "Client logo (SVG, AI, CDR, PDF, EPS)",
            type=ext_list,
            key=f"client_logo_upload_{FORM_KEY}_{st.session_state['logo_uploader_id']}",
        )
        if st.button("Clear uploaded logo", width="stretch", key=f"clear_logo_{FORM_KEY}"):
            _clear_artwork_state()
            st.session_state["logo_uploader_id"] = int(st.session_state["logo_uploader_id"]) + 1
            st.rerun()

    missing = []
    if not client.strip():
        missing.append("client")
    if not family:
        missing.append("product family")
    elif family == "poncho":
        missing.append("a poncho worksheet (not available yet)")
    if not product_keys:
        missing.append("products")
    if family == "umbrella" and not panel_config:
        missing.append("panel configuration")
    if not fabric:
        missing.append("fabric")
    if not logo_color:
        missing.append("logo color")
    if year is None:
        missing.append("worksheet year")

    if missing:
        st.warning("Fill the job ticket to build a proof: " + ", ".join(missing) + ".")
        render_project_guide(stamp_version=STAMP_VERSION)
        return

    resolved_knockout = knockout_mode
    job = JobSpec(
        client=client.strip(),
        panel_config=panel_config,
        panel_count=panel_count,
        product_keys=product_keys,
        family=family or "umbrella",
        fabric_name=fabric,
        logo_color_name=logo_color,
        request_date=request_date.strip() or "—",
        last_update=last_update.strip() or "—",
        project_owner=owner.strip() or "—",
        print_order=print_order.strip() or "—",
        year=int(year),
        knockout_white=resolved_knockout == "white",
    )
    job.knockout_mode = resolved_knockout

    memory.remember_ui(
        {
            "client": job.client,
            "panel_config": panel_config,
            "panel_count": panel_count,
            "products": product_keys,
            "family": family,
            "fabric": fabric,
            "logo_color": logo_color,
            "project_owner": job.project_owner,
            "print_order": job.print_order,
            "request_date": request_date,
            "knockout_white": job.knockout_white,
        }
    )

    logo = None
    logo_bytes = None
    logo_name = None
    if upload is not None:
        logo_bytes = upload.getvalue()
        logo_name = upload.name
        st.session_state["logo_bytes"] = logo_bytes
        st.session_state["logo_name"] = logo_name
    else:
        # Do not preload a saved Proper (or any) logo — wait for an explicit upload.
        st.session_state.pop("logo_bytes", None)
        st.session_state.pop("logo_name", None)
        st.session_state.pop("_saved_logo", None)

    if logo_bytes and logo_name:
        try:
            logo = load_artwork(logo_bytes, logo_name)
        except VectorLoadError as exc:
            st.error(str(exc))
            return
        stamp = date.today().isoformat()
        saved = LOGO_DIR / f"{job.client.replace(' ', '_')}_{stamp}_{Path(logo_name).name}"
        if st.session_state.get("_saved_logo") != saved.name:
            saved.write_bytes(logo_bytes)
            logger.log("logo_upload", {"client": job.client, "file": saved.name, "bytes": len(logo_bytes)})
            st.session_state["_saved_logo"] = saved.name
        st.success(f"Using uploaded artwork: `{logo_name}` · {job.logo_color_name}")
    else:
        st.info("No client logo uploaded. Official Proper marks are removed; upload SVG/AI/CDR/PDF/EPS to stamp.")

    logo_fp = _logo_fingerprint(logo_bytes, logo_name)
    job_fp = (
        f"{STAMP_VERSION}|{job.client}|{job.family}|{job.panel_config}|{job.panel_count}|"
        f"{','.join(job.product_keys)}|{job.fabric_name}|{job.logo_color_name}|"
        f"{job.request_date}|{job.last_update}|{job.project_owner}|{job.print_order}|"
        f"{job.year}|{job.knockout_mode}|{job.knockout_white}|{logo_fp}"
    )
    prev_fp = st.session_state.get("_job_fingerprint")
    if prev_fp != job_fp:
        # Drop any cached preview from a prior fabric/logo/upload so nothing overlays.
        _clear_preview_cache()
        st.session_state["_job_fingerprint"] = job_fp

    left, right = st.columns([2, 1], vertical_alignment="top")
    with left:
        st.badge(job.client_label, color="gray", icon=":material/checkroom:")
        st.subheader("Production worksheet")
        with st.spinner("Updating worksheet preview…"):
            pages = _preview_pages(
                STAMP_VERSION,
                job.client,
                job.panel_config,
                job.panel_count,
                tuple(job.product_keys),
                job.family,
                job.fabric_name,
                job.logo_color_name,
                job.request_date,
                job.last_update,
                job.project_owner,
                job.print_order,
                job.year,
                job.knockout_mode,
                job.knockout_white,
                logo_fp,
                logo_bytes,
                logo_name,
            )
        if not pages:
            st.warning("No official worksheet pages for the selected styles.")
        else:
            tabs = st.tabs([title for title, _jpeg in pages])
            for tab, (title, jpeg) in zip(tabs, pages):
                with tab:
                    st.image(jpeg, caption=title, width="stretch")

    with right:
        st.subheader("Export")
        page_plan = exporter.page_plan(job)
        page_labels = [title for _no, title in page_plan]
        st.write(
            f"**File:** `{worksheet_filename(job.client, job.year, job.family)}`  \n"
            f"**Fabric:** {fabric_caption(job.fabric_name)}  \n"
            f"**Logo:** {job.logo_color_name}  \n"
            f"**Placement:** {panel_config}  \n"
            f"**Pages ({len(page_plan)}):** {' · '.join(page_labels) or '—'}"
        )
        if not logo:
            st.caption("No upload yet — Generate exports the worksheet with logo slots cleared.")
        generate = st.button(
            "Generate production worksheet PDF",
            type="primary",
            icon=":material/picture_as_pdf:",
            width="stretch",
        )
        if generate:
            with st.spinner(f"Composing {len(page_plan)}-page worksheet…"):
                pdf_bytes = exporter.build_pdf(job, logo)
            out_name = worksheet_filename(job.client, job.year, job.family)
            out_path = OUTPUT_DIR / out_name
            out_path.write_bytes(pdf_bytes)
            st.session_state["pdf_bytes"] = pdf_bytes
            st.session_state["pdf_name"] = out_name
            st.session_state["pdf_pages"] = page_labels
            st.session_state["pdf_fingerprint"] = job_fp
            logger.log(
                "pdf_export",
                {
                    "client": job.client,
                    "products": job.product_keys,
                    "pages": page_labels,
                    "fabric": job.fabric_name,
                    "file": out_name,
                    "bytes": len(pdf_bytes),
                },
            )
            st.success(f"Wrote `{out_name}` · {len(page_labels)} pages: {' · '.join(page_labels)}")

        # Keep download outside the Generate click so Streamlit can finish serving the file.
        pdf_bytes = st.session_state.get("pdf_bytes")
        pdf_name = st.session_state.get("pdf_name")
        pdf_pages = st.session_state.get("pdf_pages") or []
        pdf_fp = st.session_state.get("pdf_fingerprint")
        if pdf_bytes and pdf_name:
            if pdf_fp and pdf_fp != job_fp:
                st.warning("Job ticket changed since the last PDF. Generate again to include the current styles.")
            else:
                st.caption(f"Ready to download · {len(pdf_pages)} pages: {' · '.join(pdf_pages)}")
            st.download_button(
                "Download PDF",
                data=pdf_bytes,
                file_name=pdf_name,
                mime="application/pdf",
                icon=":material/download:",
                width="stretch",
                key="download_worksheet_pdf",
            )

    st.caption(
        "Catalog: Walk · Stick · Golf Essential / 62 / 68 · Trek · Travel · Collapsible · Kids. "
        "Artwork bound 21.6 × 10 cm (Walk/Golf). Logos: SVG, AI, CDR, PDF, EPS."
    )
    render_project_guide(stamp_version=STAMP_VERSION)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 — Cloud "Oh no" hides the real traceback
        _tb = traceback.format_exc()
        print(_tb, flush=True)
        try:
            st.error("The app failed while starting. Traceback is below.")
            st.code(_tb, language="text")
        except Exception:
            pass
