# Modelling

One learner family, deliberately. The interesting engineering is not the
choice of gradient booster; it is leakage discipline, honest evaluation,
calibrated uncertainty and knowing when *not* to serve a model.

## 1. Target and features

**Target:** `load_kw`, itself `DERIVED` from the published energy counter (see
[data provenance](data_provenance.md#3-the-unit-problem-and-how-it-was-resolved)).

**Feature families** (`core/models/features.py`):

| Family | Features |
|---|---|
| Calendar | time-of-day sin/cos, day-of-week sin/cos, season sin/cos, hour, weekday, weekend |
| Occupancy calendar | scheduled day-off, public holiday, and their union `is_closed` |
| Weather | outdoor temperature, 1 h lag, 6 h and 24 h means |
| Degree-hours | heating and cooling degree-hours about the site's **published** base temperature, plus 24 h means |
| Lags | 1 d, 1 d + 15 min, 2 d, 3 d, 5 d |
| Rolling | mean and std over 1 d / 3 d / 5 d of the 1-day-shifted target |
| Shape | yesterday's value at this hour ÷ yesterday's daily mean |

### Leakage, controlled by construction

Every feature is calendar, weather, or a lag of **at least 24 hours**. The floor
is a module constant and lags are checked against it at build time:

```python
MIN_LAG_STEPS = STEPS_PER_DAY          # 96 steps = 24 h
if lag < MIN_LAG_STEPS:
    raise ValueError(f"lag {lag} is shorter than the leakage floor {MIN_LAG_STEPS}")
```

This is also asserted as a property: perturbing only the final sample must not
change any earlier feature row (`tests/test_models.py`). A feature that read the
present would move a row it has no business moving.

### Why lags stop at 5 days

The source's usable stretches are contiguous **10-day blocks**. A feature
reaching back 7 days would be unavailable for most of any window worth
replaying, so the 10 days are budgeted:

```
|<---------------- one 10-day source block ---------------->|
|<------ 5 days: feature lookback ------>|<-- 3 days: replay -->|  (+2 slack)
```

An earlier build used a weekly lag — the single strongest feature by gain — and
then had no window where six sites were simultaneously complete. The 5-day cap
is a data constraint made explicit, not a modelling preference.

## 2. Evaluation

Splits are strictly chronological, and there are **two** of them because they
answer different questions.

```
|<--------------- history (before the demo window) --------------->|<-- demo window -->|
|<--- 60% fit --->|<-- 20% calibrate -->|<---- 20% backtest ------->|<---- live ------->|
```

- **fit** — trains the boosters.
- **calibrate** — early stopping *and* the conformal offset. Never trains.
- **backtest** — model quality. Large enough for the numbers to mean something.
- **live** — the window the demo replays, held out entirely by the cutoff.
  Small, so it is reported as evidence rather than as a performance claim.

### The baseline is the strongest naive candidate

Skill is reported against the **best** of `lag_96`, `lag_288` and `lag_480`,
chosen per split. Picking a weak reference to flatter the model would be the
easiest way to make these numbers meaningless.

### Results (backtest, training cutoff 2017-08-24)

| Site | n | MAE (kW) | WAPE | R² | vs best naive | Interval coverage | Live WAPE | Live coverage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 062 | 4 518 | 3.04 | 11.8% | 0.729 | **+29.8%** | 68.1% | 7.5% | 88.1% |
| 143 | 3 511 | 285.40 | 9.2% | 0.911 | **+64.6%** | 73.1% | 9.2% | 77.7% |
| 162 | 3 452 | 6.86 | 10.5% | 0.835 | **+21.3%** | 71.1% | 9.9% | 73.1% |
| 227 | 4 057 | 3.99 | 7.5% | 0.891 | **+3.4%** | 96.3% | 14.0% | 80.1% |
| 269 | 12 314 | 8.08 | 36.7% | 0.724 | **+27.0%** | 82.2% | 24.6% | 88.1% |
| 284 | 5 329 | 72.95 | 22.4% | 0.619 | **+37.2%** | 82.7% | 20.9% | 84.8% |

All six beat their baseline. Site 227 — the BMS lead building — beats it by only
3.4%, which is stated rather than hidden; its absolute accuracy (7.5% WAPE,
R² 0.891) is the best in the portfolio.

WAPE is reported alongside MAPE because several sites pass through zero, where
MAPE explodes and stops meaning anything.

## 3. Uncertainty

Two extra LightGBM boosters on the pinball loss at q=0.1 and q=0.9, then
**conformalised** (Romano, Patterson & Candès, 2019):

```
E_i  = max(lower_i − y_i, y_i − upper_i)        nonconformity on the calibration split
Q    = ceil((n+1)·0.8)-th order statistic of E
band = [lower − Q, upper + Q]
```

Raw quantile heads are over-confident under distribution shift. The offset is a
single number fitted on data the boosters never saw, and it works:

| Site | Raw coverage | Conformalised | Target |
|---|---:|---:|---:|
| 284 | 55.3% | **82.7%** | 80% |
| 143 | 63.3% | **73.1%** | 80% |
| 062 | 62.2% | **68.1%** | 80% |
| 269 | 81.0% | **82.2%** | 80% |

CQR guarantees marginal coverage on *exchangeable* data. Time series are not
exchangeable, which is exactly why coverage is then **measured** on a later
split rather than claimed. Two sites still fall short; that is reported in the
model card instead of being smoothed over.

## 4. Anomaly detection

Four lines of arithmetic, because an operator has to believe the alarm at 03:00:

```
residual   = actual − expected
centre/MAD = median and median absolute deviation of the residual
score      = 0.6745 · (residual − centre) / MAD
anomalous  = |score| > 3.5, sustained for ≥ 3 intervals, and material
```

**Median/MAD, not mean/σ** — a handful of genuine faults must not inflate the
band used to detect them.

**Materiality floor** — ≥ 2 kW *and* ≥ 8% of expected. A 0.2 kW miss on a quiet
night is statistically enormous and operationally meaningless.

**Sustain requirement** — three intervals. A single sample is telemetry far more
often than it is plant.

### The baseline is calibrated on history, not a trailing window

This is the part that matters, and it was found the hard way. The first build
used a trailing rolling median/MAD. When scenarios were wired up, **nothing was
ever flagged**: the injection spanned the whole replay window, so the rolling
baseline absorbed it and the fault became the new normal.

The baseline is now fitted on a reference period that **ends where the period
under test begins**, and conditioned on hour of day — a building's forecast
error at 03:00 and at 14:00 are not the same random variable. It is then held
fixed. There is a regression test for exactly this failure
(`test_reference_baseline_does_not_absorb_a_window_long_fault`).

### Classification is rule-based on purpose

`OVER_CONSUMPTION`, `UNDER_CONSUMPTION`, `OFF_HOURS_LOAD`, `FLATLINE`,
`SENSOR_DRIFT`, `MISSING_DATA`. Every rule is inspectable, and the UI shows the
evidence: score, residual, duration and the asset's normal miss. No black box
decides what an operator is told.

Drift is judged on the **six hours leading into** a finding, not on the finding
itself, and requires the bias to have grown by ≥ 1.5 MAD across that lead-in.
Without that scale test, ordinary residual autocorrelation reads as drift and
every finding gets the label — which is what happened before the gate was added.

Findings say **"possible causes"** and never assert one.

## 5. The serving gate

A trained model is not automatically the thing served:

```python
if model.metrics.backtest.skill_vs_baseline_pct > MIN_SKILL_PCT:   # 1%
    serve the model
else:
    serve the seasonal-naive reference it failed to beat — and say so
```

Serving a model that lost to persistence would make every downstream anomaly and
recommendation worse than doing nothing. When the gate fires, the UI marks the
row `naive`, the provenance changes, and the reason is on the model card.

## 6. The zone thermal model

A lumped 2R2C zone with an explicit plant (`core/adapters/building/simulation.py`):

```
T_out ──R_oa── T_air ──R_am── T_mass
                 │
              Q_hvac + Q_int + Q_sol

C_air  dT_air/dt  = (T_out−T_air)·UA + (T_mass−T_air)·h + Q_int + Q_sol + Q_hvac
C_mass dT_mass/dt = (T_air−T_mass)·h
```

Explicit Euler at the 15-minute control step, stable for these time constants
(τ_air ≈ 0.8 h, τ_mass ≈ 11 h). Parameters derive from published floor area
using standard commercial-office figures, and **every one is reported in the
result** so a reviewer can argue with the physics rather than the conclusion.

### The plant is ideal-load, not proportional

A proportional controller leaves a steady-state offset that swamps the very
experiment the Control Lab exists to run: with one, raising the setpoint from
23 °C to 24 °C changed energy by **+0.2%**. The plant now computes the heat flow
that lands the air node on the nearer setpoint within installed capacity — the
EnergyPlus `IdealLoadsAirSystem` formulation — and the same change gives a
credible **−10.8% over 0.6 K**, about −13% per K.

### Heating and cooling setpoints are scheduled separately

Deriving heating as `cooling − deadband` made a 27 °C summer setback imply a
25 °C heating setpoint, and the model **heated the building in August**. That
one bug had inflated the apparent AI saving from 10.8% to 39%. Dual setpoints
come from the comfort band; the deadband is now a *minimum separation*.

### Calibrated against the meter

The conditioned area is scaled until the simulator's baseline HVAC power matches
the HVAC share implied by the site's own metered weather sensitivity. One free
parameter with a physical meaning — the conditioned area the measured load
implies — rather than a fudge factor on the answer. Without it, the thermal and
electrical models describe different buildings and the cross-module impact
figure is meaningless. For site 227: 862 m² conditioned of 1 142 m² published.

## 7. Known limitations

- **No solar irradiance** in the source, so solar gain is a clipped daylight
  sinusoid. Stated in the result's assumptions.
- **No zone-level telemetry**, so the thermal model is single-zone and cannot
  be validated against measured zone temperature — only against whole-site
  electrical demand.
- **Weather is the recorded observation**, standing in for a vendor forecast.
  In production the feature would be a forecast with its own error; the model
  card says so.
- **3-day replay window.** A data constraint, not a design choice.
- **Two sites' intervals under-cover** (68% and 73% against 80%). Reported.
- **Anomaly labels are heuristics**, not diagnoses, and the UI says so.
