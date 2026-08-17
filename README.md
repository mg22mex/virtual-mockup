# Weatherman Virtual Mockup Creator

Internal Streamlit app that stamps client logos onto official Weatherman production worksheets and exports multi-page PDFs.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

System tools used for vector logos (optional locally): `rsvg-convert`, Ghostscript, ImageMagick, Poppler (`pdftocairo`).
Cloud uses PyMuPDF instead so apt installs are not required.

## Logo uploads

Accepted formats: **SVG, AI, CDR, PDF, EPS** (no PNG/JPG).

## Streamlit Community Cloud

1. Push this repo to GitHub.
2. At [share.streamlit.io](https://share.streamlit.io), create an app pointing at `app.py`.
3. In **Advanced settings**, set **Python version to 3.12** (avoid the platform default 3.14).
4. `requirements.txt` installs Python deps (including PyMuPDF for logo vectors). No apt `packages.txt` — keeps cold boots fast.
5. If logs show `spawn error` / `Event loop is closed`, use **Reboot app** from the Cloud dashboard after the latest push.

### Keep-awake (GitHub Actions)

`.github/workflows/keepalive.yml` opens the Cloud URL with Playwright **every 2 hours** (and on demand) so Community Cloud is less likely to show “get this app back up.” Run it manually from the Actions tab anytime (**Keep Streamlit awake** → Run workflow).

To change cadence, edit the `cron` in that workflow (examples: every hour `20 * * * *`, every 3 hours `20 */3 * * *`).

Note: keep-alive reduces sleep; it does not skip a full environment rebuild after changing dependencies or rebooting the app.
