# Interview demo — 5 minutes

Press **Guided demo** in the header for the scripted version. This is the same
route with the talking points.

**Before you start:** press **Reset demo** in the status bar. It clears every
server-side cache and restores the default scenario.

---

## 0. The status bar (10 s)

> "Three indicators, always visible. Data: the Schneider/DrivenData public
> dataset. AI: six models online. Simulation: which engine is actually running.
> If any of those degrades, this bar says so — it never quietly falls back."

---

## 1. BMS Overview — measured (45 s)

Go to **EcoTwin BMS → Overview**.

> "Three days of real 15-minute metered demand with the nearest published
> weather station. Note the badges. Outdoor air is **MEASURED**. Building load
> is **DERIVED** — and that is the most important thing on this screen."

Click the badge on **Building load**.

> "The publisher never states a unit for its energy counter. Values span eleven
> orders of magnitude across sites, so they are not all the same unit. Rather
> than pick a scale factor, I tested the hypothesis that it is watt-hours per
> interval by converting to power density and checking it against the band a
> commercial building can physically occupy. Sites that failed were excluded,
> not rescaled. That is why this says DERIVED, and the assumption is right
> here."

Press **play** on the replay control.

> "One clock drives the whole platform, so the building view and the power view
> are always on the same instant."

---

## 2. Prediction and detection (60 s)

> "The dashed line with the band is the forecast — LightGBM, day-ahead, with a
> conformalised 80% interval. It was trained only on data from before this
> window, so what you are watching is genuinely out of sample."

Open **Model card**.

> "Two evaluations. The backtest is a proper holdout inside the training
> history: 7.5% WAPE, R² 0.89. The live column is this window — smaller, so I
> report it as evidence rather than as a claim. Skill is measured against the
> *strongest* naive baseline, not a straw man. And look at the interval: the raw
> quantile heads under-covered at 55% on one site; conformal calibration brings
> it to 83%."

Go to **AI Operations**. Note the finding already in the normal day.

> "That is a real event in real data — 23 kW below expected at two in the
> morning, ten times this building's normal forecast miss."

Click **Hot Day / HVAC Stress**.

> "Seeded, deterministic, additive — the measurement is kept alongside it. The
> detector scores the forecast residual against an hour-of-day baseline
> calibrated on history that *ends where this window begins*. My first version
> used a trailing rolling baseline and flagged nothing: the injection spanned
> the whole window, so the baseline absorbed it and the fault became the new
> normal. There is a regression test for exactly that."

Expand a finding.

> "Observed, expected, deviation, the score against the threshold, how long it
> held, and this asset's normal miss. It says *possible causes*, never a
> diagnosis."

---

## 3. Recommendation and the safety gate (45 s)

> "A constrained setpoint proposal with the factors it responded to. Note what
> it does **not** say: no energy saving. It refuses to claim a number before the
> simulator has run."

Click **Run safety gate**.

> "Allowlist, min/max, rate limit, comfort envelope, and 'simulation target
> only'. Real historical mode is read-only and there is no code path to a real
> actuator."

---

## 4. Control Lab (50 s)

Click **Simulate in Control Lab**.

> "Baseline against AI control, both run through the same engine over identical
> weather and occupancy. 10.8% less HVAC energy and 6.6% lower peak, for two
> hundredths of a degree-hour of comfort give-away — one interval, just outside
> the band. It is a trade, and the panel shows both sides of it."

Point at the engine pill.

> "This says EcoTwin RC, not BOPTEST. There is a real BOPTEST client in here and
> local Docker mode runs it live, but this deployment cannot reach one — so a
> 2R2C zone model with an ideal-load plant ran it, and the result is labelled
> with the engine that actually answered."

If asked about the physics:

> "Every parameter is on screen. The plant is ideal-load rather than
> proportional because a proportional controller leaves a steady-state offset
> that swamped the experiment — the setpoint change moved energy by 0.2%.
> And heating and cooling setpoints are scheduled separately: deriving heating
> as cooling minus a deadband made the model heat the building in August, which
> had inflated the apparent saving from 10.8% to 39%."

---

## 5. EMS Portfolio and Network (45 s)

Go to **EcoTwin EMS → Portfolio**, then click a facility.

> "The same meters as an electrical estate. Transformer ratings are DERIVED —
> the dataset publishes no nameplate data, so they come from each site's
> observed peak by standard sizing practice, and the badge says so."

On **Power Network**:

> "pandapower solving a balanced AC load flow over a six-bus LV model with
> catalogue cable impedances. Bus voltages, feeder loading, losses — all
> SIMULATED. The feeder split is a stated disaggregation of the measured total
> using an HVAC sensitivity fitted to this site's own weather response. It is
> not four sub-meters that do not exist."

---

## 6. Scenario Lab — the flagship (75 s)

Go to **Scenario Lab**, click **EV Charging Surge**.

> "A 120 kW charging session on the flexible feeder. The transformer goes to
> **138%** of nameplate."

Click **Run flexible-load optimisation**.

> "A linear program shifting EV charging and buying HVAC flexibility. Peak 201
> down to 141 kW. EV energy is conserved as a hard equality — this defers load,
> it does not shed it. And deferral has to precede recovery: my first version
> recovered energy hours before it curtailed any, which meant charging cars that
> had not arrived. Energy balance alone does not imply causality."

Point at **Verified by load flow**.

> "139% to 96%, voltage recovering from 0.958 to 0.972 per unit. Those are two
> independent pandapower solves at the worst instant. The optimiser does not get
> to mark its own homework."

Click **Open BMS analysis & simulate HVAC action**.

> "And this is the whole point of one platform rather than two dashboards. EMS
> names the flexible contributors, BMS answers by running its *simulator* —
> baseline and proposal — and hands back an HVAC reduction in kW, and EMS
> re-solves the network with it applied. A thermal simulation feeding an
> electrical simulation. Every step is a real computation."

---

## 7. Close (20 s)

Click any provenance badge.

> "Measured, predicted, simulated, optimised, derived, injected. Six categories,
> one closed vocabulary, and two of the rules are validators in the backend: a
> value cannot be tagged MEASURED unless its registered source is a real
> measurement, and cannot be tagged SIMULATED without naming the engine that
> produced it. A mislabelled number fails at construction rather than reaching
> a chart."

---

## Questions worth being ready for

**"Is any of this real?"**
The data is: a Schneider Electric / DrivenData public competition dataset,
267 sites, real meters, real weather. The models are trained on it. The physics
and the network are models, labelled as models. What is *not* real is any claim
to a live customer system, and the footer says that on every page.

**"Why not BOPTEST here?"**
It is implemented and runs in local Docker mode. Hosting a Modelica emulator for
a portfolio demo is a poor trade. The important part is that swapping engines
does not change a single line above the adapter, and the UI never mislabels one
as the other.

**"Why does one model only beat naive by 3%?"**
Because that is what it does, and the site with the *best* absolute accuracy is
the one with the smallest skill margin — its load is highly repeatable, so
persistence is already strong. There is a gate: below 1% skill the platform
serves the seasonal-naive reference instead and marks the row.

**"How would this connect to EcoStruxure?"**
Two abstract classes, four methods each. `BuildingSourceAdapter` becomes an EBO
adapter, `PowerSourceAdapter` becomes a PME adapter. Nothing above them knows
where the numbers came from — that is the whole reason the boundary is there.

**"What would you do next?"**
Sub-metering, so the feeder split stops being a disaggregation. A second
building so the thermal model can be validated against measured zone
temperature. Probabilistic peak risk instead of a point forecast against a
threshold. And a model registry — the cards are already emitted as JSON.

**"What is the weakest part?"**
The thermal model. It is calibrated against whole-site electrical demand
because there is no zone telemetry to calibrate against, so it is credible
physics rather than a validated model of a specific building. The Control Lab
is honest about that — every parameter is on screen — but it is the claim I
would most want measured data behind.
