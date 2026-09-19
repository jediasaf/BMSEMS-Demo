# Data provenance

> The rule this project is built around: **never present a synthetic value as a
> measurement.** Everything below is how that rule is enforced rather than
> merely intended.

## 1. What was actually used

| | |
|---|---|
| Source | **Power Laws: Forecasting Energy Consumption** |
| Publisher | Schneider Electric / DrivenData (public competition dataset) |
| Landing page | <https://www.drivendata.org/competitions/51/electricity-prediction-machine-learning/> |
| Contents | 267 anonymised sites, 5–30 min metered consumption, per-site floor area, base temperature, weekly day-off calendar, nearest-station outdoor air temperature, public-holiday calendar |
| Size | ~1.4 GB across four CSV files |
| Vendored? | **No.** `data/raw/` is git-ignored; `make data` re-downloads it |

Files and columns are not assumed. `scripts/inspect_data.py` reads whatever is
present and writes `docs/schema_report.md` — dtypes, timestamp ranges, sampling
intervals, missingness, identifier cardinality and candidate targets. The
adapter layer is written against that report.

## 2. What was looked for and not found

The brief suggested a Schneider **Technopole / Grenoble** building digital-twin
dataset. It was searched for and **no publicly downloadable dataset was found**.
Public material describes the campus and its BIM-derived digital twin, but no
open time-series release was locatable.

Rather than invent one:

- `core/adapters/building/technopole.py` ships **dormant**. It watches
  `data/raw/technopole/`, validates any files it finds against a declared
  schema, and activates automatically — or fails loudly. It never fabricates.
- The real analytics run on the Power Laws dataset above, which is genuinely
  Schneider-published and genuinely open.
- Sites are named exactly as the publisher anonymises them — `Site 227`. No
  street address, campus name or building identity is invented.

If a Technopole release appears, drop it in the watch directory. Nothing else
changes.

## 3. The unit problem, and how it was resolved

**The publisher does not state a unit for `Value`.** Values range from 0 to
6.4 × 10¹¹ across sites, so they are certainly not all the same unit.

Guessing a scale factor per site would have been the easy lie. Instead:

1. **Hypothesis.** `Value` is energy in **Wh consumed during the preceding
   15-minute interval**, so `load_kw = Value × 4 ÷ 1000`.
2. **Test.** Convert to a power density using the site's *published* floor
   area, and check it against the band a commercial building can physically
   occupy: **3–120 W/m²**.
3. **Decision.** Sites that fail are **excluded**, not rescaled. 71 sites had
   enough 15-minute data; **39 passed** the unit and weather checks.
4. **Consequence.** Every kW figure in the platform is tagged **`DERIVED`,
   never `MEASURED`**, and the assumption travels with it in the provenance
   popover.

This is the single most important honesty decision in the project. A dashboard
that prints "487 kW · MEASURED" from this dataset is wrong, and there is no way
to tell from the dashboard alone.

## 4. Choosing the demo window

The source is not a continuous history: every usable stretch is a **contiguous
10-day block**, with gaps between blocks. That hard constraint shapes three
things at once, and `scripts/prepare_data.py` resolves them together.

| Constraint | Consequence |
|---|---|
| Blocks are 10 days | lookback + replay ≤ 10 days |
| The forecaster's deepest lag is 5 days | 5 days of the block go to features |
| A replay needs more than one day | 3-day window is what remains |
| A portfolio needs several sites at once | window must be dense for ≥ 6 sites |
| The demo must be out-of-sample | ≥ 90 dense days must precede the window |
| Load and weather come from different files | both must be ≥ 98% complete |

The selected window — **2017-08-24 to 2017-08-27**, 3 days, 6 sites — is the
one that maximises the portfolio's average daily load swing subject to all of
the above. A flat-profile site makes a worse demo than a smaller portfolio with
real daily structure, so the search optimises quality, not count.

**Training stops at the window.** Every model is fitted on data strictly before
`2017-08-24`, so the replay shows genuinely out-of-sample predictions. This is
the only version of that claim worth making.

## 5. The six provenance categories

| Badge | Meaning | Example here |
|---|---|---|
| `MEASURED` | Read from a published measurement, at most resampled | Outdoor air temperature from the nearest station |
| `DERIVED` | Deterministic arithmetic on measurements plus published metadata | `load_kw`, power density, transformer ratings, the occupancy proxy |
| `PREDICTED` | Output of a forecasting model | Expected load and its interval |
| `SIMULATED` | Output of a physics or network solver | Zone temperature, transformer loading, bus voltages |
| `OPTIMISED` | A proposed setpoint or dispatch from a constrained optimiser | Setpoint trajectory, EV/HVAC dispatch |
| `INJECTED` | A seeded scenario disturbance added by EcoTwin | Hot-day offset, EV charging surge |

Two rules are **validators on the model**, not conventions:

```python
# core/provenance/model.py
if self.source_type is SourceType.MEASURED and not descriptor.is_real_measurement:
    raise ValueError(f"source {self.source_key!r} is not a real measurement ...")
if self.source_type is SourceType.SIMULATED and self.engine is None:
    raise ValueError("SIMULATED provenance must name the simulation engine")
```

A mislabelled value fails at construction rather than reaching a chart, and
only sources registered in `core/provenance/sources.py` can be cited at all.

## 6. Things this dataset cannot support, and what was done instead

| Not published | What EcoTwin does |
|---|---|
| Occupancy | A **stated proxy**: load normalised between its open-day 5th and 95th percentiles, damped on calendar-closed days. Tagged `DERIVED`, labelled "Proxy" in the UI. |
| Zone topology / floor plan | A hierarchy generated from published floor area. Only the building node is `MEASURED`; every generated node carries a note saying so. |
| Zone temperature | Does not exist in the source. It comes from the Control Lab simulator and is tagged `SIMULATED`. |
| Sub-meters | The network model's feeder split is a **documented disaggregation** of the measured total, using an HVAC sensitivity fitted to each site's own weather response. Never presented as measured sub-metering. |
| Transformer nameplate | **Derived** by standard sizing: smallest IEC rating covering the site's P99 at pf 0.95 with 25% headroom. The assumption appears on every loading figure. |
| Tariffs, emission factors | **Nothing is shown.** No cost or CO₂ figures anywhere, because configuring either would be an invention. |

## 7. Data quality, in the open

Every asset has a data-quality drawer reporting expected vs actual samples,
missingness, duplicate timestamps, sampling interval, outlier count and rule,
flatline runs, units, last timestamp and the source files.

Known characteristics of the processed set:

- Gaps up to one hour are filled by time interpolation and flagged
  `INTERPOLATED`; longer gaps stay `MISSING` and the forecaster drops those rows
  rather than imputing them.
- Timestamps carry **no UTC offset**. They are treated as a consistent local
  clock and never converted. The API coerces any tz-aware instant a client
  sends to naive rather than shifting it.
- Outdoor temperature is published half-hourly and upsampled to the 15-minute
  grid, so it is `MEASURED` where observed and `INTERPOLATED` where filled.
- Only the **nearest** weather station is used per site; mixing stations at
  different distances injects a step change a model would learn as signal.

## 8. If the data is missing entirely

Delete `data/raw` and `data/processed` and the application still runs. The
adapter registry falls back to `core/adapters/*/fixture.py`, every value is
tagged `SAMPLE FIXTURE`, the status bar switches to `SAMPLE FIXTURE` mode, and
`describe_source()` carries a warning. The fixtures are seeded and physically
motivated — a base load, a Gaussian occupancy profile and a degree-day HVAC
response — so the AI layer is exercised on a realistic shape, but no fixture
number can be mistaken for a measurement.

## 9. Disclaimer

This portfolio prototype does not connect to a live Schneider Electric customer
environment. Public Schneider data are used for analytics. Building and
electrical control experiments are performed using simulation environments.
