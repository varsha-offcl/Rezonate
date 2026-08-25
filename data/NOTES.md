# Data cleaning notes

Source: OPSD `time_series_60min_singleindex` (through 2020-06-30 for the
Berlin weather overlap) joined with Open-Meteo Berlin weather archive
(2016-01-01 onward), inner-joined on UTC hourly timestamp.

- **Range after join:** 2016-01-01 00:00 to 2020-06-30 23:00, 39,432 hourly
  rows, no missing timestamps, no gaps other than 1h steps (checked by
  diffing the index).
- **DST:** none observed, because both sources are in UTC. No discontinuity
  handling needed.
- **solar_mw / wind_mw:** 63 NaNs each (0.2%), forward-filled up to 3h in
  `loader.py`. Longest zero-run in solar is 15h, consistent with winter
  nights (not a sensor dropout). No negative values in solar/wind/load.
- **price_eur_mwh (`DE_LU_price_day_ahead`):** 61% NaN. This is not a data
  quality defect — Germany, Austria and Luxembourg were a single bidding
  zone until the market split on 2018-10-01; the `DE_LU_price_day_ahead`
  column simply doesn't exist before that date in this OPSD release. Price
  is not used until the cost-objective phase (GA/PSO), so this is deferred:
  when needed, either restrict price-dependent work to the post-2018-10-01
  window or source a pre-split DE/AT/LU price series separately.
- **solar_capacity_mw / wind_capacity_mw:** 11% NaN, all in the second half
  of 2020 where the OPSD capacity series simply stops updating before the
  file's end. Not used as a forecast target, only as an optional context
  feature; left as-is.
- **load_mw / load_forecast_tso_mw:** effectively complete (0% and 0.1% NaN).

Figures: `results/figures/01_full_series_overview.png` (full 2016-2020
range, all series) and `results/figures/02_sample_week.png` (June 2019,
generation/load/price detail).
