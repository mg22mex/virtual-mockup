# Weatherman Virtual Mockup Creator

Internal Streamlit app that stamps client logos onto official Weatherman production worksheets and exports multi-page PDFs.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

System tools used for vector logos: `rsvg-convert`, Ghostscript, ImageMagick, Poppler (`pdftocairo`).

## Logo uploads

Accepted formats: **SVG, AI, CDR, PDF, EPS** (no PNG/JPG).

## Streamlit Community Cloud

1. Push this repo to GitHub.
2. At [share.streamlit.io](https://share.streamlit.io), create an app pointing at `app.py`.
3. In **Advanced settings**, set **Python version to 3.12** (avoid the platform default 3.14).
4. `requirements.txt` and `packages.txt` install Python and apt dependencies automatically.
5. If logs show `spawn error` / `Event loop is closed`, use **Reboot app** from the Cloud dashboard after the latest push.
