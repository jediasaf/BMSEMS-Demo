# EcoTwin AI — interview demo script

A five-minute run through both workflows. No slides. Every number below was
produced by the engines named in its provenance, and none of it is hardcoded.

**Which of the two modes you are in**

| | Hosted link | `make demo` |
|---|---|---|
| What it is | a **recording** of a real run, served as files | the real thing, solving on request |
| Needs | a browser | Python, the dataset, ~1 GB of RAM |
| First click | instant | instant once warm, a few seconds cold |
| Can it be interrogated | click anything, drag the replay slider | that, plus change the code and re-run |

Both show the same numbers, because the recording was taken from the live
system. **Say which one you are in, in your first sentence.** A replay
presented as a live computation is the one thing in this project that would
be worth failing over, and the product says so itself: a `RECORDED` chip with
the date sits in the status bar, and every payload carries a `_snapshot`
marker.

If you have five minutes and a laptop, run it live — "is it actually
computing?" is the question the hosted link cannot answer on its own.

**Running it live**

```bash
make demo          # or: bash scripts/dev_restart.sh
curl -s localhost:8000/interview/verify | jq .ready     # must print true
```

`ready: true` means the ten claims this script makes have just been checked
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
> competition, 267 anonymised sites at 15-minute resolution. That dataset ends
> in November 2017, so the clock reads 2017: I replay the archive against its
> own timestamps rather than shifting them forward to look current. Two
> operational workflows over one provenance model: a building operator and a
> power operator.
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

> "Under the chart the dashboard answers the two questions an operator
> actually has. **Forecast**: the highest point the model expects in the next
> twelve hours, when it lands, and the 80% interval it came with — a point
> estimate on its own would be the wrong thing to put in front of someone who
> has to act on it. **Optimisation**: what the setpoint plan would save over
> the next day, and whether the simulator accepted it."

**Point at:** the interval, and the verdict pill. Both are the honest half of
their panel.

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

> "Below the risk chart, the dispatch it implies: peak down 60 kW, the
> transformer from 139% to 96%, and 168 kWh of charging **moved rather than
> shed**. On a day with no overload that panel says there is nothing to
> dispatch and names the loading it actually reaches — it does not run the
> optimiser to print a row of zeroes."

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

**Click: `Run optimisation`.** The guided bar does not press it for you, and
step 10 has nothing to talk about until you do. It is the only button in the
demo that computes on demand — a convex solve and two load flows, about 80 ms
— so press it while you are saying the sentence above, not before.

### Step 10 — verify

> "The before and after transformer figures are **two independent pandapower
> solves** at the worst instant, not the optimiser's own estimate.
> **139.4% → 96.0%**, and every bus back inside the EN 50160 band.
>
> Underneath is the network verdict, which is the EMS twin of the simulator's
> veto on the building side. Seven criteria, all read off the *post-action*
> load flow: it converged, the transformer is at or under nameplate, every bus
> is inside EN 50160, the solver reported no violations, loading actually
> fell, and — re-checked outside the solver, against the arrays served to this
> page — the EV energy was **deferred, not shed**: 168.3 kWh out, 168.3 kWh
> back. A solver that returns `optimal` has confirmed its own program. It has
> not confirmed the network."

**Point at:** the seven criteria with their measured margins.

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
| You are on the hosted link and someone asks whether it is live | `RECORDED` chip with the date, in the status bar | "It is a recording of a real run — same engines, same code paths, written to files so the demo needs no server. `make demo` runs it live in about a minute if you want to watch it compute." |

The recording cannot degrade the way the live system can: the failures in the
first four rows are live-mode failures. What a recording *can* do is go stale,
which is why `scripts/verify_snapshot.py` re-checks it against the same claims
`/interview/verify` checks.

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
