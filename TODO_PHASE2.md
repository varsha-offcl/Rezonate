# Phase 2 — Resume checklist (TFT + LSTM)

Paused mid-Phase-2 at the user's request: **do not train on CPU**. All code is
written and smoke-tested; only the actual training run + the steps that depend
on its outputs remain. Resume here once the GPU is available.

_Last updated: 2026-08-03._

---

## State at pause

**Done and verified**

- Environment fixed: `.venv` was pointing at another machine's Python; repointed
  `.venv/pyvenv.cfg` to local `Python311`. Phase 1 pipeline re-verified
  end-to-end (loader → splits → metrics → baselines → export → frontend build).
- `requirements.txt` added (pinned, numpy pinned <2 because pytorch-forecasting
  1.1.1 needs it — Phase 1 baselines produce identical numbers under numpy 1.26.4).
- Phase-2 deps installed into `.venv`: `torch==2.5.1+cpu`, `lightning==2.4.0`,
  `pytorch-forecasting==1.1.1`. **torch is the CPU build** — see GPU step below.
- `src/forecasting/tft.py` written and **smoke-tested on GPU** (`--fast` runs the
  whole pipeline: multi-target TFT + LSTM train 1 epoch on a tiny slice,
  evaluate, extract importance, write `results/phase2_*.json`). Trainer is
  GPU-ready (`accelerator="auto"`). The GPU eval device bug (CUDA tensor →
  numpy) is **fixed** (`_to_np` helper).
- `src/export/to_json.py` extended to merge TFT bands + LSTM + importance, with a
  clean fallback to baseline-only when `results/phase2_*.json` are absent.
- Frontend: `ForecastChart.jsx` (model switcher + TFT P10–P90 band, degrades
  gracefully without Phase-2 data), `VariableImportance.jsx` (**wired into
  `App.jsx`**, shows a friendly placeholder until `importance.json` exists),
  `MetricsTable.jsx` labels updated. Lints + builds clean.
- Whole chain validated end-to-end with fast data (train → export → valid JSON →
  frontend build). Shipped `frontend/public/data/*.json` reset to honest
  baseline-only until real training runs.

**Not done (needs GPU training)**

- Real TFT + LSTM training run (CPU was ~6 min/epoch → too slow; halted). Once a
  CUDA torch build is installed, this is just steps 1–3 below — no code changes.

---

## Resume steps (in order)

### 1. Install a CUDA build of PyTorch

The venv currently has CPU-only torch. Replace it with a CUDA build matching the
GPU's driver (check `nvidia-smi`; cu121 is a safe default for recent drivers):

```bash
.venv/Scripts/pip uninstall -y torch
.venv/Scripts/pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu121
.venv/Scripts/python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

Expect `True`. (If Windows Application Control blocks the CUDA DLLs — the policy
noted in README — fall back to the CPU build and train overnight instead.)

### 2. Train both models

```bash
.venv/Scripts/python -m src.forecasting.tft --model both --max-epochs 30
```

Writes `results/models/{tft,lstm}.ckpt` and `results/phase2_{metrics,forecast,importance}.json`.
Early stopping (patience 5 on `val_loss`) usually ends well before 30 epochs.
Sanity-check: TFT test nRMSE should beat persistence (Phase-1 numbers are in
`MetricsTable`); if TFT ≈ LightGBM or worse, tune hidden_size / learning_rate /
epochs on validation only (never test).

### 3. Re-export for the dashboard

```bash
.venv/Scripts/python -m src.export.to_json
```

Should print `Merging Phase-2 models: ['tft', 'lstm']` and write `importance.json`.

### 4. Rebuild the dashboard

`VariableImportance` is already wired into `App.jsx`, so no code change is
needed — just rebuild:

```bash
cd frontend && npm run build && npm run dev
```

Verify in the browser: model switcher lists TFT/LSTM, the TFT band renders as a
shaded P10–P90 region, and the importance card shows past/known-future weights.

---

## Design decisions locked in (for the report)

- **One multi-target model** forecasts solar/wind/load jointly (1 TFT + 1 LSTM,
  not 6) — far cheaper and a valid joint formulation.
- **TFT** = quantile loss P10/P50/P90 (probabilistic). **LSTM**
  (`RecurrentNetwork`) = MAE point forecast, the deterministic comparison arm on
  identical splits / equal budget. Both compared on RMSE/MAE/nRMSE vs baselines.
- **Weather actuals used as known-future covariates** = perfect-weather-foresight
  idealisation; in deployment these would be weather forecasts. State this in the
  report as a limitation.
- **Price excluded** from covariates (61% NaN pre-2018 bidding-zone split); it is
  not a forecast target and is deferred to the GA/PSO cost phase.

## Open tuning ideas if TFT underperforms

- Increase `max_encoder_length` context or `hidden_size` (plan allows tuning on val).
- Try `EncoderNormalizer` instead of `GroupNormalizer` for non-stationary series.
- Add lag features / `add_relative_time_idx` variants.
- Longer training now that the GPU makes epochs cheap.
