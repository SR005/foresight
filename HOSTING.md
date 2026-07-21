# Hosting FORESIGHT as a website

The dashboard is a Streamlit app. The fastest free way to put it online is
**Streamlit Community Cloud** (no server to manage, gives you a public URL like
`https://foresight-northbay.streamlit.app`).

---

## Option A — Streamlit Community Cloud (recommended, free)

### 1. Push the repo to GitHub

From the `foresight/` folder:

```bash
git init
git add .
git commit -m "Project FORESIGHT — demand & inventory intelligence"
git branch -M main
git remote add origin https://github.com/<your-username>/foresight.git
git push -u origin main
```

The `.gitignore` already keeps the raw workbook and the 19 MB `sales_daily.csv`
out, while **committing the small model outputs the app needs**
(`forecast.csv`, `risk_scores.csv`, `weekly_panel.csv`, and the JSON summaries,
~1.5 MB total). That's what lets the hosted app load instantly without
re-running the pipeline.

### 2. Deploy

1. Go to **https://share.streamlit.io** and sign in with GitHub.
2. Click **Create app → Deploy a public app from GitHub**.
3. Fill in:
   - **Repository:** `<your-username>/foresight`
   - **Branch:** `main`
   - **Main file path:** `app/streamlit_app.py`
4. Click **Deploy**. First build takes ~2–3 minutes while it installs
   `requirements.txt`.

You'll get a public URL you can share. The theme in `.streamlit/config.toml`
(indigo `#1F1F3D` / accent `#6B6BD6`) is applied automatically.

### 3. Refresh the data later

Re-run the pipeline locally, then push:

```bash
python src/run_all.py
git commit -am "refresh forecast" && git push
```

Streamlit Cloud redeploys on every push.

---

## Option B — Hugging Face Spaces (also free)

1. Create a new **Space** → SDK **Streamlit**.
2. Upload the repo (or connect the GitHub repo).
3. Set the app file to `app/streamlit_app.py`.
   Spaces reads `requirements.txt` automatically.

---

## Option C — Render / Railway (a always-on container)

Start command:

```bash
streamlit run app/streamlit_app.py --server.port $PORT --server.address 0.0.0.0
```

Use this if you also want the FastAPI scoring service online — deploy
`service/main.py` as a second service:

```bash
uvicorn service.main:app --host 0.0.0.0 --port $PORT
```

---

## Run it locally first (to check it before deploying)

```bash
cd foresight
pip install -r requirements.txt
streamlit run app/streamlit_app.py
# opens http://localhost:8501
```

If the page says "No model outputs found", run `python src/run_all.py` once to
generate `data/processed/`.

---

### Notes

- **Free tiers sleep when idle** and wake on the next visit (a few seconds) —
  fine for a demo / portfolio link.
- Don't commit the raw client data or secrets — the `.gitignore` handles this.
- The dashboard and the API are independent; you can host just the dashboard.
