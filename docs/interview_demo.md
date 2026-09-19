# EcoTwin AI — interview demo script

A five-minute run through both workflows. Everything below is produced by the
running system; no slide, no recording, nothing hard-coded.

**Where to run it**

The public frontend is https://ecotwin-ai-zeta.vercel.app (SSO-protected).
It has no backend yet, so **run the demo locally** until one is deployed:

**Before you start**

```bash
make demo          # or: bash scripts/dev_restart.sh
curl -s localhost:8000/interview/verify | jq .ready     # must print true
```

`ready: true` means the eight claims this script makes have just been checked
against real computation. If it prints `false`, the failing check names which
half of the story broke — read it before you start, not during.

Open `http://localhost:3000`. It opens straight into the BMS overview: there
is no landing page. Click **Start demo** in the sidebar. That resets the
product to its opening position, preloads every curated computation, and opens
the guided bar at step 1. **Next demo step** advances; **Back** reverses; the
scenario and the route are re-applied on every step, so a stray click cannot
knock you off course.

The numbers quoted below are the ones the system produces for site 227 on the
2017-08-24 → 2017-08-27 replay window. They are stable across restarts: every
scenario is seeded from `sha256(scenario_id | asset_id)`, not from `hash()`.

---

## 00:00–00:30 — What this is

> "EcoTwin AI is a portfolio prototype, not a Schneider Electric product. It
> runs on Schneider's own published dataset — the Power Laws forecasting
> competition, 267 anonymised sites at 15-minute resolution. Two operational
> workflows over one provenance model: a building operator and a power
> operator.
>
> The bar across the top never goes quiet. It tells you where the data came
> from, how many models are serving, which simulator is live, and where the
> replay clock is. Right now it says the zone simulator is the EcoTwin RC
> engine, because BOPTEST is not reachable from this deployment — and it will
> keep saying that rather than quietly labelling RC results as BOPTEST."

**Point at:** the system bar. **Technical point:** the product is honest about
its own degradations before you ask.

---

## 00:30–02:30 — BMS: detect → explain → recommend → simulate

### Step 1 — the building as recorded

> "Real metered demand, replayed against its own clock. Note the badge on the
> load: **DERIVED**, not measured. The publisher never states a unit for its
> energy counter — so the kW figure is a hypothesis I validated by a
> power-density check, and the badge says so. Outdoor air is **MEASURED**,
> because that one is published as °C."

**Click:** any provenance badge. The popover gives source, publisher, field,
units, processing and assumptions.

### Step 2 — inject the disturbance

> "A hot day. Seven kelvin on outdoor air with a mid-afternoon emphasis, and
> the load follows through this building's own fitted cooling sensitivity. It
> is **additive** — the measurement is untouched and both series stay charted —
> and the banner says INJECTED SCENARIO. I am not going to pretend a
> disturbance I wrote is something the building did."

### Step 3 — detection

> "The detector scores the forecast residual as a robust z against an
> hour-of-day baseline. The baseline is calibrated on history that *ends where
> this window begins*. That matters: a rolling baseline adapts to a fault that
> lasts the whole window and never flags it. I had that bug — the scenarios
> produced zero insights — and the fix is a regression test now.
>
> Observed against expected, the deviation, how long it was sustained, and how
> it compares with this asset's normal forecast miss. The causes are labelled
> **possible** and 'not a diagnosis', because a residual cannot tell you which
> of three things happened."

**Expected:** 2 findings on the curated scenario.

### Step 4 — the recommendation

> "A constrained setpoint proposal: raise the occupied cooling setpoint from
> 23 to 24. Its contributing factors, the constraints it was checked against,
> a confidence, and a safety gate you can run. Notice the expected impact says
> **no number is claimed until the simulator has run**. A recommendation that
> quotes a saving before simulating it is guessing."

### Step 5 — simulate, and let the simulator judge

> "The optimiser is a linear program over the same two-node zone model the
> simulator integrates — air node and structure, 0.8-hour and 11-hour time
> constants — with installed plant capacity as a box constraint and the COP as
> a per-step price. Delivered cooling is the decision variable.
>
> Then the implied setpoint trajectory goes back through the full nonlinear
> simulator, and this panel is the simulator's verdict, not the optimiser's.
> **−11.9% HVAC energy, −8.4% peak, 0.035 K·h of comfort given up.** Both
> columns are the same engine over identical weather and occupancy.
>
> And the gate can say no. I modelled the air node alone at first; a
> single-node model thinks overnight pre-cooling is cheap, proposed exactly
> that, and the simulator came back −0.4% energy and **+58% peak**. That is
> what 'simulate before you actuate' has to mean: the simulation has a veto,
> and a rejected proposal claims no saving."

**Point at:** the four acceptance criteria with their measured margins.

---

## 02:30–04:30 — EMS: forecast → overload → optimise → resolve

### Step 6 — the portfolio

> "The same metered facilities as an electrical estate. Transformer ratings
> are **DERIVED** from each site's observed peak by standard sizing practice,
> because this dataset publishes no nameplate data, and the badge says so —
> that would be the easiest lie in the whole project. Capacity is calibrated
> by bisection on the load flow, not by kVA × power factor: a 160 kVA unit
> gives 144.9 kW of real demand at exactly 100% loading."

### Step 7 — the EV surge

> "A 120 kW charging session on the flexible feeder each afternoon, ramping
> over 30 minutes. This is load the transformer was never sized for. The Peak
> Demand scenario, by contrast, does *not* break it — a correctly sized
> transformer survives its own peak day, and the instructive result is the one
> where nothing goes wrong."

### Step 8 — what it does to the network

> "pandapower, balanced AC load flow, six-bus LV model with catalogue XLPE
> impedances. Forecast peak **200.8 kW against a 144.9 kW capacity — 138.5%**,
> at 16:00. The LV bus sags. Every number here is a solve, and every one is
> labelled SIMULATED with the engine named."

**Click:** the transformer in the single-line diagram for the detail panel and
the contributors at the peak.

### Step 9 — optimise

> "A linear program over the flexible resources. EV energy is conserved as a
> **hard equality** — the vehicles get their kilowatt-hours — and recovery can
> never precede curtailment, enforced as a cumulative-sum constraint. I had
> that bug too: the optimiser was charging vehicles that had not arrived yet.
> HVAC flexibility is bought against a comfort energy budget.
>
> **168.3 kWh of EV charging deferred, peak 200.8 → 140.6 kW.**"

### Step 10 — verify

> "The before and after transformer figures are **two independent pandapower
> solves** at the worst instant, not the optimiser's own estimate.
> **139.4% → 96.0%**, and every bus back inside the EN 50160 band."

---

## 04:30–05:30 — Provenance and architecture

### Step 11 — provenance

> "Six categories, one closed vocabulary, enforced in the backend. Two of them
> are validators rather than conventions: a value cannot be tagged MEASURED
> unless its registered source is a real measurement, and cannot be tagged
> SIMULATED without naming the engine that produced it. A mislabelled number
> fails at construction rather than reaching a chart.
>
> There is also an audit — `scripts/audit_provenance.py` — that walks every
> served payload against a manifest and fails if a metric loses its badge. It
> found three real gaps when I wrote it, including one panel drawing a
> hardcoded MEASURED pill over a derived number."

### Step 12 — architecture

> "Both pipelines end to end. The thing I would emphasise is the adapter
> layer: it is the only code that knows a source's field names, which is what
> makes this EcoStruxure-ready rather than EcoStruxure-shaped. Swapping the
> Power Laws adapter for an EBO or PME adapter does not touch the forecaster,
> the detector, the optimiser or the simulator.
>
> And no actuation. Historical mode is read-only and there is no code path to
> a real controller."

---

## If something is unavailable

The demo is built to degrade in public rather than fail.

| What fails | What you see | What to say |
|---|---|---|
| BOPTEST unreachable | System bar reads `EcoTwin RC engine`; the Control Lab banner explains it | "BOPTEST is optional. The engine that ran is named on every result; local Docker mode runs BOPTEST where it is reachable." |
| Preload did not finish | Interview pill reads `· on demand` | "It computes on click instead of ahead of time. Slower, identical numbers." |
| A panel errors | Red "Panel unavailable" with the message and a Retry | "Each panel fails alone. The rest of the page is still true." |
| No processed dataset | Everything reads `SAMPLE FIXTURE` | "Deterministic synthetic stand-in. Every value carries SAMPLE FIXTURE in provenance — it cannot be mistaken for real." |
| A model failed its quality gate | Row marked `naive`, gate reason in the tooltip | "The model is only served if it beats the strongest naive baseline by 1%. Otherwise you get seasonal-naive and a reason." |

If the guided bar gets out of step, click **Reset demo**: it restores the
route, the replay cursor, both scenarios, every selection and every computed
result.

---

## Numbers worth having in your head

| | |
|---|---|
| Dataset | Power Laws: Forecasting Energy Consumption, 1.03 M records, 2013-05-30 → 2017-11-20 |
| Replay window | 2017-08-24 → 2017-08-27, 15-minute steps |
| BMS site / EMS facility | 227 (1,142 m²) / 227 (160 kVA) |
| Control Lab | −11.9% energy, −8.4% peak, +0.035 K·h comfort |
| Transformer capacity | 144.9 kW at 100% loading (bisection on the load flow) |
| EV surge | 200.8 kW peak, 138.5% loading at 16:00 |
| After optimisation | 140.6 kW, 96.0% by an independent load flow, 168.3 kWh deferred |

Every one of these is re-derived on each run. If a model changes and a number
moves, `/interview/verify` and `tests/test_interview.py` will say so before an
audience does.
