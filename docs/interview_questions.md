# Technical questions, and honest answers

Written for the questions an engineer actually asks. Where a choice has a real
cost, the cost is stated rather than defended.

---

### Why LightGBM and not deep learning?

Because the data does not justify anything larger, and I can defend every
decision it makes.

Each site has a few years of 15-minute demand with a weather series and a
calendar. That is a tabular problem with strong calendar and lag structure —
exactly where gradient boosting is hard to beat. An LSTM or a temporal fusion
transformer would need far more data per site to justify its parameter count,
would take orders of magnitude longer to train across 267 sites, and would
give me a worse answer to "why did it predict that".

There is also a serving argument. Per-site gradient boosting models are a few
hundred kilobytes each and predict in milliseconds on CPU, so the demo has no
GPU dependency and no inference service. If a site's model cannot beat the
strongest naive baseline by 1% on a chronological backtest, it is not served
at all and the UI says which reference it fell back to.

**What I gave up:** cross-site transfer. A per-site model learns nothing from
the other 266. With a fleet this size, a global model with site embeddings is
the obvious next step, and it is where I would spend the next week.

---

### Why residual anomaly detection rather than an anomaly model?

Because a residual is explainable and a learned anomaly score is not.

The detector scores `measured − expected` as a robust z — `0.6745·(r − centre)
/ MAD` — against an hour-of-day baseline. When it fires, I can put observed,
expected, the deviation, the threshold, how long it was sustained and how that
compares to the asset's normal forecast miss on screen. An operator can agree
or disagree with each of those. An isolation forest gives a number between 0
and 1 and nothing to argue with.

It is also robust where it needs to be: MAD rather than standard deviation, so
the anomalies themselves do not inflate the threshold they are measured
against, and a materiality floor in kW so a 3σ deviation on a 2 kW night load
does not become an alert.

**The bug worth mentioning:** the baseline was originally a trailing rolling
window. A fault lasting the whole replay window slowly became the new normal
and the detector reported nothing — the scenarios produced zero insights. It
is now calibrated on a reference period that *ends where the tested window
begins*, and there is a regression test named after the failure.

**What I gave up:** anything multivariate. A residual detector on one channel
will not catch a fault that keeps total demand normal while changing its
composition. Sub-metering would let me score per-feeder residuals, which is
where I would take it.

---

### Why BOPTEST?

Because a savings claim needs a simulator somebody else wrote.

BOPTEST is the IBPSA project's building-emulator benchmark: peer-reviewed test
cases, a REST API, and results other people can reproduce. If I claim a
setpoint change saves 12%, the useful version of that claim is "here is the
test case, here is the control signal, run it yourself".

In this deployment BOPTEST is not reachable, so an in-process 2R2C model with
an ideal-load plant runs the case instead. That is stated in the system bar
and on the Control Lab, and every result carries the engine that produced it
in provenance — `SimulationResult.engine` is not optional, and a value cannot
be tagged SIMULATED without naming an engine. An RC result is never labelled
BOPTEST. The engine is behind a `BuildingSimulationEngine` interface, so
pointing `BOPTEST_URL` at a reachable instance switches it with no other
change.

**What I gave up:** the external validation that was the point. The RC model
is calibrated against this site's own metered weather sensitivity, which makes
it plausible rather than verified.

---

### Why pandapower?

Because the EMS story is about a transformer, and a transformer constraint is
a load-flow result.

pandapower is the standard open-source power-system analysis tool for exactly
this: a balanced AC Newton–Raphson solve over a network with real component
models. I could have written `demand / (kVA × pf)` in one line, but then the
bus voltages would be decoration, the losses would be invented, and the
"verified by load flow" claim would be circular.

Using a real solver bought three things I could not fake: cable impedances
from a catalogue so feeder loading is physical; bus voltages that can be
checked against the EN 50160 band; and an independent second solve to verify
the optimiser's answer rather than trusting its own estimate.

It also changed a number I had wrong. Transformer capacity was `kVA × pf`,
which gave 147 kW for a unit that actually reached 100% loading at 144.9 kW —
the difference is the losses and the voltage drop. Capacity is now found by
**bisection on the load flow**: increase demand until the solver reports
100.0%.

**What I gave up:** unbalanced and harmonic analysis. Single-phase EV charging
on a three-phase LV feeder is genuinely a phase-balance problem, and this
model cannot see it.

---

### Why not connect directly to EcoStruxure?

Because I do not have a customer environment, and inventing one would be the
least defensible thing in the project.

What I did instead is make the source a boundary. `core/adapters/` is the only
code that knows a source's field names, units or quirks; everything above it —
forecaster, detector, optimiser, simulator, provenance — works on a common
internal schema. Swapping the Power Laws adapter for an EBO adapter is one
class implementing `BuildingSourceAdapter`, and nothing downstream changes.

That is what "EcoStruxure-ready architecture" means here, and it is the limit
of what I will claim. The product says "not an official Schneider Electric
product" on the About page and in the API root response.

---

### How would EBO integration actually work?

EcoStruxure Building Operation exposes BACnet/IP and a REST API over its
object model. The adapter would:

1. **Discover** — walk the object hierarchy to build the asset tree, instead
   of the tree this prototype synthesises from floor area. Real zones, real
   AHUs, real points.
2. **Read** — subscribe to trend logs for the points the models need: zone
   temperature, setpoints, supply air, valve positions, meters. Present-value
   polling for the live cursor.
3. **Map** — translate EBO object types to the internal schema, and attach a
   `Provenance` naming the EBO server, object id and trend interval as the
   source. Everything measured becomes genuinely MEASURED for the first time.
4. **Write, eventually** — EBO can accept a setpoint write at a priority
   level. I would not enable it without the three things this prototype
   already has plus two it does not: the point allowlist and range limits it
   has, the simulator's veto it has, plus an operator confirmation step and a
   time-bounded revert. Priority 8 (operator override) with an automatic
   relinquish is the standard pattern.

The honest sequencing is read-only for months first. Nothing in this prototype
writes to anything: there is no code path from a recommendation to a
controller, only to a simulator.

---

### How would PME integration work?

Power Monitoring Expert is a SQL Server historian with a documented schema and
an ODATA layer. Simpler than EBO, because it is a measurement archive rather
than a control system.

The adapter would query the measurement tables for per-meter real power,
current and voltage, and — this is the important part — replace two things
this prototype has to derive. Transformer nameplates would come from the
asset register instead of being sized from observed peaks, and feeder-level
demand would be measured instead of disaggregated. The pandapower model would
then be validated against measured voltages rather than only solved.

---

### How would this scale?

The demo is 6 sites. The published dataset is 267. A real estate is thousands.

- **Storage**: Parquet files are right for a fixed archive and wrong for
  ingestion. The first change is TimescaleDB or ClickHouse — hypertables on
  `(asset_id, timestamp)`, continuous aggregates for the rollups the portfolio
  view recomputes on every request.
- **Training**: per-site models are embarrassingly parallel; 267 sites took
  minutes on one machine. At thousands, this becomes a scheduled job with a
  model registry and staleness monitoring, not a script.
- **Serving**: the expensive operations are the load flow and the zone
  simulation, both CPU-bound and both cacheable by `(asset, scenario,
  instant)`. Everything else is a lookup.
- **The real constraint** is not compute, it is the adapter layer. Two
  thousand buildings means two thousand point-naming conventions, and the
  mapping is where the work goes. That is an argument for the adapter boundary
  being the thing I got right.

I deliberately did not add Kubernetes or a message bus. At this size they
would be architecture theatre.

---

### How do you prevent unsafe control actions?

Four layers, and the third one is the one I would talk about.

1. **No actuation path.** There is no code from a recommendation to a
   controller. Historical mode is read-only. A recommendation's `mode` is
   `ADVISORY` or `SIMULATION`; nothing else exists.
2. **A validation gate** (`core/optimisation/validation.py`): an allowlist of
   writable points, absolute range limits, a maximum step per change, and a
   rate limit. A proposal outside any of them is refused with the reason.
3. **The simulator's veto.** The optimiser plans against a linear model. The
   proposal is re-run through the full nonlinear simulator and scored against
   the baseline on energy, peak and comfort — and **rejected** if it does not
   improve on doing nothing. This is not hypothetical: the first version of
   the optimiser proposed overnight pre-cooling that came back +58% on peak,
   and the gate is what turns that from a shipped regression into a rejected
   proposal.
4. **Comfort as a constraint, not an objective.** The zone band is a hard
   constraint with penalised slack, and the comfort cost of every accepted
   proposal is reported in K·h next to the saving.

For a real deployment I would add operator confirmation, a time-bounded revert
window, and a kill switch that relinquishes every override — none of which
this prototype needs, because it cannot write.

---

### How do you know the savings are real?

I do not claim they are real. I claim they are what a named simulator produced
from a stated model, and I show the model.

- Both cases run through the **same engine** with identical weather and
  occupancy. The only difference is the setpoint trajectory.
- Every model parameter is on screen — all twenty-one of them, on purpose.
- The zone model is calibrated against this site's own metered weather
  sensitivity: conditioned area is scaled so simulated baseline HVAC power
  matches the HVAC share estimated from the meter. That is stated, with the
  numbers, in the Zone Calibration panel.
- The comfort cost is reported alongside the saving. A saving with no comfort
  column is a saving that moved the discomfort somewhere you are not looking.
- The proposal must pass the acceptance gate, and a rejected proposal shows
  its numbers greyed and marked "not claimed as a saving".

What would make it real is measurement and verification against an IPMVP
option — a baseline model, a reporting period, and adjusted comparison. That
needs the intervention to actually happen, which needs the actuation path this
prototype deliberately does not have.

---

### How do you prevent leakage?

Three mechanisms, and the first one is structural rather than procedural.

1. **A lag floor in the feature builder.** No feature may use data newer than
   96 steps — 24 hours — before the target. This is enforced where features
   are constructed, not by remembering to be careful. Rolling statistics are
   computed on already-lagged series.
2. **Chronological splits.** Fit, calibrate, backtest and live are contiguous
   and ordered. No shuffling, no k-fold.
3. **A training cutoff at the demo window.** Models are trained strictly on
   data before the replayed window, so the replay is genuinely out of sample.
   I added this after realising the first models had been trained on the
   window the demo replays — the forecast looked excellent for the wrong
   reason.

The prediction intervals are conformalised (Romano et al., 2019) on a
dedicated calibration split, which is also where under-coverage shows up
honestly: two facilities under-cover their nominal 80%, and the model card
reports it rather than smoothing it over.

---

### Why simulate before actuating, if you already have an optimiser?

Because the optimiser and the plant do not solve the same problem.

The optimiser needs a convex model to give a certifiable global optimum in
milliseconds. That model is an approximation — here, a two-node linear zone
with a capacity box and a per-step COP price. The real plant saturates, the
COP moves continuously, and the controller is an ideal-load loop, not a power
schedule.

So the optimiser proposes and the simulator judges. Concretely: my first
optimiser modelled the air node alone. Air capacitance gives a 0.8-hour time
constant; the structure gives 11 hours. A single-node model believes overnight
pre-cooling is cheap and effective, so it proposed it — and the nonlinear
simulator reported **−0.4% energy and +57.7% peak**, because the zone drifted
and the plant recovered into the hottest, worst-COP part of the afternoon.

Two fixes, both worth having: the optimiser now runs the same two-node model
the simulator integrates, and the simulator has a veto regardless. The second
fix is the one that generalises, because there will always be a next modelling
error.

---

### How do you distinguish measured from simulated values?

A closed vocabulary with validators, not a naming convention.

Six categories: MEASURED, DERIVED, PREDICTED, SIMULATED, OPTIMISED, INJECTED.
Every value-bearing object carries a `Provenance` with source, publisher,
field, units, processing and assumptions. Two of the rules are Pydantic
validators:

- A value cannot be tagged **MEASURED** unless its registered source is a real
  measurement. The source registry is closed — citing an unregistered key
  raises, which caught a typo of mine during this work.
- A value cannot be tagged **SIMULATED** without naming the engine that
  produced it.

A mislabelled value fails at construction rather than reaching a chart.

That covers mislabelling but not omission, so there is also
`scripts/audit_provenance.py`: it walks every served payload against a
manifest of the metrics that matter and fails on a missing badge, an
unexpected category, or a path that no longer resolves. It runs in CI. When I
wrote it, it found three real gaps — including the Building View drawing a
hardcoded MEASURED pill over a number whose own KPI badge said DERIVED.

The one worth understanding is **DERIVED versus MEASURED**. The site meter is
a measurement. The kW figure shown for it is not: the publisher never states a
unit for the energy counter, so kW is a hypothesis — Wh per 15-minute interval
— that I validated by checking power density lands in a plausible 3–120 W/m²
band, excluding the sites that failed rather than rescaling them. Every kW
series in the product is therefore DERIVED, and the popover says exactly that.

---

### What would you do next?

In order of how much they would change what the product can claim:

1. **Reach BOPTEST**, so the savings have external validation instead of a
   plausible internal model.
2. **Sub-metering or an EBO feed**, so zones stop being pro-rata allocations
   and the detector can work per-feeder.
3. **A global forecaster with site embeddings**, so a new site is not a cold
   start.
4. **Unbalanced load flow**, because single-phase EV charging on a three-phase
   feeder is a phase problem this model cannot see.
5. **Measurement and verification**, once anything can actually be actuated.

What I would not do next is add models. The limit here is data and validation,
not architecture.
