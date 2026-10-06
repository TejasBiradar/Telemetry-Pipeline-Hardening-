# System Diagrams: Telemetry Pipeline Hardening

> DRAFT. Reflects the current design; the pipeline source (Q1/Q2) is still open.
> Colours show the owner: **A** Understand & Protect · **B** Detect · **C** Prove & Operate · **Shared**.

## 1. Overall system architecture
```mermaid
flowchart TB
    subgraph SRC["Telemetry sources — synthetic"]
        GEN["Event generator<br/>web / iOS / Android<br/>multiple client versions"]
        INJ["Fault injector<br/>unit change, missing field,<br/>new nulls, text change..."]
    end

    subgraph LEG["Supplied pipeline — read-only"]
        S1["Stage 1: Ingest"]
        S2["Stage 2: Clean"]
        S3["Stage 3: Enrich / Aggregate"]
        OUT[("Pipeline output<br/>dashboard metrics")]
    end

    subgraph UND["Understand & Protect"]
        CG["Code graph<br/>modules, functions, fields"]
        GUA["GUARANTEES.md<br/>reconstructed rules"]
        CT["Characterisation tests<br/>golden outputs"]
        LIN["Lineage map<br/>source → field → stage → metric"]
        EQ["Equivalence check<br/>before vs after"]
    end

    subgraph DET["Detect — guard library"]
        CON["Contracts<br/>rules per checkpoint"]
        GATE["Quality gates<br/>schema, nulls, range,<br/>units, volume"]
        ND["Numeric drift"]
        TD["Text payload drift"]
        AM["Alert manager<br/>group, attribute source,<br/>severity"]
    end

    subgraph PRV["Prove & Operate"]
        EV["Evaluation engine<br/>precision, recall, lag<br/>vs baselines B0/B1"]
        API["FastAPI"]
        UI["React dashboard"]
        CI["CI evaluation gate<br/>blocks bad merges"]
    end

    DB[("PostgreSQL<br/>events, check results,<br/>alerts, lineage, eval")]

    GEN --> INJ --> S1
    S1 -->|hook| GATE
    S1 --> S2
    S2 -->|hook| GATE
    S2 --> S3
    S3 -->|hook| GATE
    S3 --> OUT

    LEG -. read code .-> CG
    CG --> GUA --> CON
    CG --> LIN
    LEG -. pin behaviour .-> CT
    CT --> EQ

    CON --> GATE
    GATE --> ND
    GATE --> TD
    GATE --> AM
    ND --> AM
    TD --> AM
    LIN --> AM

    AM --> DB
    INJ -. ground truth .-> DB
    OUT --> DB
    DB --> EV
    DB --> API --> UI
    EV --> CI
    EQ --> CI

    classDef a fill:#dbeafe,stroke:#1d4ed8,color:#0b1b3f
    classDef b fill:#dcfce7,stroke:#15803d,color:#052e16
    classDef c fill:#fef3c7,stroke:#b45309,color:#3b1d00
    classDef legacy fill:#f3f4f6,stroke:#6b7280,color:#111827
    classDef shared fill:#ede9fe,stroke:#6d28d9,color:#1e1b4b

    class CG,GUA,CT,LIN,EQ a
    class CON,GATE,ND,TD,AM b
    class GEN,INJ,EV,API,UI,CI c
    class S1,S2,S3,OUT legacy
    class DB shared
```

## 2. What happens to one batch at runtime
```mermaid
flowchart TD
    B["New batch arrives"] --> T["Tag each record<br/>source, client version, batch id"]
    T --> ST["Pipeline stage runs"]
    ST --> H{"Guard mode?"}
    H -->|off| NX["Continue unchanged"]
    H -->|observe / enforce| C1["Run gates<br/>schema, nulls, range, units, volume"]
    C1 --> C2["Run drift checks<br/>numeric + text<br/>per source & version"]
    C2 --> R{"Any check failed?"}
    R -->|no| NX
    R -->|yes| AL["Create / update alert<br/>with source + lineage"]
    AL --> M{"Mode = enforce<br/>and severity = fail?"}
    M -->|no| NX
    M -->|yes| Q[("Quarantine batch")]
    NX --> NS{"More stages?"}
    NS -->|yes| ST
    NS -->|no| O[("Write output")]
```

## 3. Evaluation & CI gate flow
```mermaid
flowchart LR
    DS["Datasets<br/>baseline · tuning · held-out eval"] --> F["Inject faults<br/>+ clean runs<br/>record ground truth"]
    F --> R0["Run B0<br/>no checks"]
    F --> R1["Run B1<br/>simple schema checks"]
    F --> R2["Run our system"]
    R0 & R1 & R2 --> MT["Match alerts to injections<br/>same field + source<br/>within N batches"]
    MT --> MX["Metrics<br/>precision · recall · lag<br/>lineage completeness"]
    EQV["Equivalence<br/>guard off vs on, clean data"] --> RP
    COV["Test coverage"] --> RP
    MX --> RP["Evaluation report<br/>+ dashboard"]
    RP --> G{"CI gate:<br/>below thresholds or<br/>outside blast radius?"}
    G -->|yes| BL["❌ Merge blocked"]
    G -->|no| OK["✅ Merge allowed"]
```

## 4. Team ownership and hand-offs
```mermaid
flowchart LR
    A["Member A<br/>Understand & Protect<br/>code graph · guarantees ·<br/>char. tests · hooks ·<br/>equivalence · lineage"]
    B["Member B<br/>Detect<br/>contracts · gates ·<br/>numeric drift · text drift ·<br/>alerts"]
    C["Member C<br/>Prove & Operate<br/>data generator · fault injector ·<br/>evaluation · CI gate ·<br/>API · UI · deployment"]
    S["Shared<br/>setup & CLAUDE.md · BRD ·<br/>security · review log · demo"]

    A -->|hidden rules → contracts| B
    A -->|lineage map| B
    A -->|lineage map| C
    B -->|checks to test| C
    C -->|results → tune thresholds| B
    C -->|test data| A
    S --- A
    S --- B
    S --- C

    classDef a fill:#dbeafe,stroke:#1d4ed8,color:#0b1b3f
    classDef b fill:#dcfce7,stroke:#15803d,color:#052e16
    classDef c fill:#fef3c7,stroke:#b45309,color:#3b1d00
    classDef s fill:#ede9fe,stroke:#6d28d9,color:#1e1b4b
    class A a
    class B b
    class C c
    class S s
```
