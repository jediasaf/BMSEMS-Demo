# Architecture

## The shape of it

```mermaid
flowchart TB
    subgraph browser["Browser"]
        UI["Next.js 15 · React 19 · TypeScript<br/>BMS: Overview · AI Operations · Control Lab<br/>EMS: Portfolio · Power Network · Scenario Lab"]
    end

    subgraph api["FastAPI backend"]
        R["Routers<br/>/bms · /ems · /link · /status"]
        SB["BmsService<br/>detect → predict → recommend"]
        SE["EmsService<br/>forecast → risk → optimise"]
        SX["CrossModuleService<br/>power ↔ building"]
        EX["ExpectedLoadService<br/>model-quality gate"]
    end

    subgraph core["core/ — source-agnostic domain"]
        AD["Adapters<br/>building · power"]
        ML["Models<br/>LightGBM · residual anomaly"]
        OPT["Optimisation<br/>CVXPY: setpoints · flexible load"]
        SIM["Simulation<br/>BOPTEST client · RC engine"]
        NET["pandapower LV model"]
        PROV["Provenance<br/>closed vocabulary + validators"]
        SCN["Scenarios<br/>seeded, deterministic"]
    end

    subgraph data["Prepared artefacts"]
        PQ[("parquet<br/>load · weather · holidays")]
        MD[("models/<br/>*.joblib + model cards")]
        DC[("demo/<br/>precomputed results")]
    end

    UI -->|JSON over HTTP| R
    R --> SB & SE & SX
    SB & SE --> EX
    SB --> ML & OPT & SIM
    SE --> ML & OPT & NET
    SX --> SB & SE
    SB & SE --> AD & SCN
    AD --> PQ
    ML --> MD
    R -.->|hosted fallback| DC
    SB & SE & SX --> PROV
```

## Two deployment targets, one codebase

```mermaid
flowchart LR
    subgraph public["Hosted interview demo"]
        direction TB
        PB["Browser"] --> PW["Next.js<br/>standalone"]
        PW --> PA["FastAPI"]
        PA --> PD[("parquet + models<br/>baked into the image")]
        PA --> PP["pandapower<br/>live, ~40 ms"]
        PA --> PC["CVXPY<br/>live, ~2 ms"]
        PA --> PR["EcoTwin RC engine<br/>live, ~0.3 s"]
        PA -.-> PX[("demo cache<br/>fallback")]
    end

    subgraph local["Local engineering mode"]
        direction TB
        LB["Browser"] --> LW["Next.js"]
        LW --> LA["FastAPI"]
        LA --> LD[("full processed dataset")]
        LA --> LP["pandapower"]
        LA --> LC["CVXPY"]
        LA --> LT["BOPTEST<br/>live Modelica emulator"]
    end
```

The only difference is which simulation engine answers, and the platform
**says which one did**. A result from the RC engine is never labelled BOPTEST;
`SimulationResult.engine` carries the truth and provenance repeats it.

## The BMS flow

```mermaid
flowchart LR
    M["Measured<br/>metered demand<br/>+ station weather"] --> D["Detect<br/>robust z of the<br/>forecast residual"]
    M --> P["Predict<br/>LightGBM + conformal<br/>interval"]
    P --> D
    D --> R["Recommend<br/>constrained setpoint<br/>proposal"]
    R --> V{"Validate<br/>allowlist · range<br/>rate · comfort"}
    V -->|blocked| X["No action"]
    V -->|passed| S["Simulate<br/>baseline and proposal<br/>through one engine"]
    S --> C["Compare<br/>energy · peak · comfort"]
```

## The EMS flow

```mermaid
flowchart LR
    M["Measured<br/>facility meters"] --> F["Forecast<br/>per-facility LightGBM"]
    F --> K["Detect risk<br/>forecast + injection<br/>vs calibrated capacity"]
    K --> O["Optimise<br/>LP over HVAC + EV<br/>energy conserved"]
    O --> S["Simulate<br/>pandapower load flow<br/>before and after"]
    S --> RS["Resolve<br/>new transformer state"]
```

## The cross-module workflow

```mermaid
sequenceDiagram
    participant EMS
    participant BMS
    participant SIM as Building simulator
    participant PP as pandapower

    EMS->>EMS: transformer risk over the forward horizon
    EMS->>BMS: which feeders are flexible, and by how much
    BMS->>BMS: optimise a setpoint trajectory (CVXPY)
    BMS->>SIM: run baseline
    BMS->>SIM: run proposal
    SIM-->>BMS: two KPI sets from one engine
    BMS-->>EMS: HVAC reduction in kW at the risk instant
    EMS->>PP: load flow, before
    EMS->>PP: load flow, after
    PP-->>EMS: transformer loading, bus voltage, losses
```

Every arrow is a real computation. The number that reaches the operator is the
output of a thermal simulation feeding an electrical simulation.

## Why the adapter boundary is where it is

```mermaid
flowchart TB
    subgraph today["Prototype"]
        T1["PowerLawsBuildingAdapter"]
        T2["FacilityPowerAdapter"]
        T3["TechnopoleAdapter<br/><i>dormant</i>"]
        T4["Fixture adapters"]
    end
    subgraph contract["Contract"]
        C1["BuildingSourceAdapter<br/>available · list_sites<br/>load_frame · describe_source"]
        C2["PowerSourceAdapter<br/>available · list_facilities<br/>load_frame · describe_source"]
    end
    subgraph future["Production"]
        F1["EcoStruxure Building<br/>Operation adapter"]
        F2["EcoStruxure Power<br/>Monitoring Expert adapter"]
    end
    T1 & T3 & T4 --> C1
    T2 & T4 --> C2
    F1 -.-> C1
    F2 -.-> C2
    C1 & C2 --> AI["AI · optimisation · simulation · UI<br/><i>unchanged</i>"]
    AI --> O1["Constrained setpoint recommendation<br/>validated, simulated, advisory"]
    AI --> O2["Flexible-load dispatch<br/>verified by a second load flow"]
```

Four methods each. The contract is deliberately narrow: metadata, a rectangular
time-series frame on a strict grid, and a description of the source. Everything
above it works on the common internal schema in `core/common/schemas.py` and has
no idea where the numbers came from.

## Layering rules

- `core/` never imports from `apps/`. It is the domain library; the API is one
  consumer and the scripts are another.
- Only `core/adapters/` knows a source's field names.
- Only `core/provenance/sources.py` may name a citable source.
- The API owns composition and HTTP concerns, not domain logic.
- The frontend owns presentation. It never computes a KPI, never converts a
  unit, and never decides a provenance badge.

## Performance, measured

Warm, median of three, against the local production build:

| Endpoint | Warm |
|---|---|
| `/healthz` (liveness; touches nothing) | 2 ms |
| `/health` (every component, including a real load flow) | 64 ms |
| `/bms/overview` | 184 ms |
| `/bms/insights` | 2 ms |
| `/bms/assets` | 27 ms |
| `/bms/control-lab` (2 simulations + a convex solve) | 838 ms |
| `/ems/portfolio` (6 facilities) | 48 ms |
| `/ems/network` (load flow) | 68 ms |
| `/ems/risk` | 29 ms |
| `/ems/optimise` (LP + 2 load flows) | 139 ms |
| `/interview/verify` (re-runs every demo claim) | 2.0 s |

Two caches earn most of that. The per-facility transformer capacity is found by
bisection on the load flow — about forty solves — and the anomaly detection
behind the overview and portfolio screens runs its classifier once per
anomalous step. Both are deterministic in their inputs, both are cached, and
both are warmed at start-up, so the first click of a demo is not the slow one.
Before the detection was cached the EMS portfolio cost 1.45 s on **every**
request; it is 48 ms now, and the answer is identical.

## What is deliberately not here

Kubernetes, PostgreSQL, TimescaleDB, LSTMs, transformers, reinforcement
learning, battery/solar/carbon/tariff optimisation, BACnet, live EBO or PME
integration, 3D geometry, a chatbot, a reporting engine. See
[Future work](#) in the README. Each of these is a real amount of work that
would not have made the two flows any more defensible.
