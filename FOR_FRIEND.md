# Quick start

Everything is included — trained models (`results/models/*.ckpt`), all data,
and the pre-exported dashboard JSON. You do **not** need to retrain or
re-download anything.

## Fastest: just see the dashboard

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

That's it — the dashboard reads static JSON already sitting in
`frontend/public/data/`, generated from the trained TFT/LSTM models.

## Full backend (optional — enables the live "what-if" sliders)

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python -m uvicorn src.api:app --port 8000
```

Then run the frontend steps above in a separate terminal.

## More detail

- `README.md` — full setup + project status
- `HANDOFF.md` — phase-by-phase history, what's done/not done
- `SUMMARY.md` — plain-language, non-technical overview
- `CHARTS.md` — what each dashboard chart shows

Note: `.env` (API key for the optional LLM explanation feature) was
intentionally left out — see `.env.example` if you want to set that up
yourself, it's free at console.groq.com.
