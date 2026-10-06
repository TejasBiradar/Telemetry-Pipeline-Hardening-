# Telemetry Pipeline Hardening: Requirements Understanding & Open Questions

> **Status:** DRAFT, to be verified with the panel/mentor before any design is frozen.
> **Source:** *C5i Capstone Projects catalogue (18 Sep)*: Brief **#31**, Technology industry, *Data Engineering & Data Modernization* practice. Also Section 02 (common guidelines), which applies to every project.
> **Rule for this document:** anything not written in the catalogue is marked **[ASSUMPTION]** or listed as an **open question**. Nothing is final until it is verified.

---

## 1. What the documents say

### 1.1 The brief (#31), word for word
| Item | Text |
|---|---|
| Business problem | Event telemetry degrades quietly: a field changes unit, a client version stops emitting, a schema gains a nullable that downstream assumed present. Nothing fails loudly, dashboards keep rendering, and the corruption is found when a number is questioned weeks later. |
| What to build | Take a **supplied** telemetry pipeline you did not write. Map it with a code graph, reconstruct what it actually guarantees, and write characterisation tests before changing anything. Then add quality checks as gates, drift detection over both numeric fields and text payloads, and alerting with lineage back to the emitting source. Inject degradations and report which checks catch them and how quickly. Keep the change inside a controlled blast radius and prove the pipeline still produces equivalent output. |
| Success metrics | Detection precision and recall on injected degradations · detection lag · output equivalence after change · characterisation-test coverage · lineage completeness |
| Key techniques | Code-graph comprehension of an unfamiliar pipeline · characterisation testing before change · quality checks as pipeline gates · numeric and payload drift detection · alert-to-source lineage |

### 1.2 Programme rules that apply to every project (Section 02)
| Area | Rule |
|---|---|
| Team | 3–4 members. **Every member owns an area and presents it.** **Scoring is individual.** Every member must also be able to answer for the whole design. |
| Build window | From **Day 3** of the 10-day programme, then **one week after Day 10**. *(Roughly 2.5 weeks, not 6.)* |
| Data | **Synthetic or public only.** No real customer data, no PII, no C5i/client data. Realistic real-format data at a volume that makes the engineering decisions real. |
| Environment | **Claude Code** as the primary build environment; Claude cloud agent for delegated/parallel work; OpenAI Codex where a comparison is useful. |
| "Done" means | **Runs** live from a clean clone · **Engineered** (standards, instruction files, skills, hooks, BRD, design, task plan in version control, plus a review log of agent output) · **Measured** (numbers vs a **baseline**, plus a **CI evaluation gate that can block a merge**) · **Secure** (scans, secrets in a manager, agent permission boundary stated) · **Operable** (non-production deployment, health checks, **demonstrated rollback**, runbook) · **Honest** (limitations stated up front) |
| Pre-pitch deliverables | Repo + README + architecture diagram · BRD with testable acceptance criteria, solution design, decision records, task plan · agent engineering record (instruction files, skills, hooks, CI gates, review log, defects caught) · evaluation report + baseline + evaluation set · security evidence · deployment evidence · 5–6 slide deck + one-page summary · live demo + recorded fallback |
| Presentation | 20 min = 15 min team + 5 min Q&A. Suggested split: 2 problem · 2 design · 2 agent usage · **5 live demo** · 3 evidence · 1 limitations. |
| Rubric | Functionality 25 · Engineering & delivery discipline 20 · Evaluation & evidence 20 · Subject-matter understanding 15 · Relevance to C5i 10 · Presentation 10 |

---

## 2. Requirements broken down

### 2.1 Functional requirements (from the brief)
| ID | Requirement | Plain meaning | Open points |
|---|---|---|---|
| **F1** | Work on a *supplied* pipeline we did not write | The input is someone else's working code | Who supplies it? → **Q1, Q2** |
| **F2** | Map it with a code graph | Build a navigable graph of modules, functions, fields and their flow | Is any specific tool expected? → **Q10** |
| **F3** | Reconstruct what it actually guarantees | Write down the implicit rules the code relies on (units, required fields, keys, ranges) | Is there an answer key to score against (as brief #03 has)? → **Q3** |
| **F4** | Characterisation tests **before** changing anything | Pin current behaviour, including behaviour that looks wrong | Coverage type? → **Q7** |
| **F5** | Quality checks **as gates** | Checks sit inside the pipeline and can stop a bad batch, not only report it | Block, or quarantine and continue? → **Q11** |
| **F6** | Drift detection on **numeric fields** | Spot distribution and unit shifts | — |
| **F7** | Drift detection on **text payloads** | Spot changes in free-text/JSON payloads | What counts as a "text payload"? → **Q12** |
| **F8** | Alerting **with lineage to the emitting source** | The alert names the source (client, version, feed) and field | What level of "source"? → **Q9** |
| **F9** | Inject degradations; report which checks catch them and how quickly | Fault-injection harness + detection report | Is there an expected fault list? → **Q5** |
| **F10** | Controlled blast radius | Our changes touch only an intended, stated part of the pipeline | How is it proven? → **Q13** |
| **F11** | Prove equivalent output | With our changes, clean data gives the same output as before | Exact or within tolerance? → **Q8** |

### 2.2 Success metrics: proposed definitions (all need confirmation)
| Metric | Proposed definition **[ASSUMPTION]** | Open question |
|---|---|---|
| Detection precision | Alerts that match a real injected fault ÷ all alerts raised | Counted per alert or per injection? → **Q6** |
| Detection recall | Injected faults detected ÷ faults injected | Same as above |
| Detection lag | Batches (and seconds) from the first bad record to the first matching alert | Unit: batches, events or time? → **Q6** |
| Output equivalence | % of output rows/metrics identical, guard off vs guard on, clean data | Exact vs tolerance → **Q8** |
| Characterisation-test coverage | Line + branch coverage of the pipeline code under characterisation tests | Line, branch, or "% of guarantees tested"? → **Q7** |
| Lineage completeness | % of alerts traced to source + field + stage + affected output | Definition → **Q9** |
| **Baseline** (required by the programme) | Proposed: the same fault set run against (a) the pipeline as supplied (no checks) and (b) naive schema-only checks | What baseline does the panel expect? → **Q4** |

### 2.3 Programme (non-functional) requirements
| ID | Requirement | What we must produce |
|---|---|---|
| **N1** | Runs from a clean clone | One-command setup; README |
| **N2** | Specification pack | BRD with testable acceptance criteria, solution design, decision records (ADRs), task plan |
| **N3** | Agent engineering record | `CLAUDE.md`/instruction files, skills, hooks, CI gates, review log of agent changes + defects caught |
| **N4** | CI evaluation gate | A merge is **blocked** when detection quality or equivalence regresses, and we demonstrate a blocked merge |
| **N5** | Security | Dependency/code scan + triage, secrets in a manager, agent permission boundary written down |
| **N6** | Deployment | Non-production target, health checks, demonstrated rollback, runbook |
| **N7** | Honesty | Limitations, residual risk, what the system refuses to do |
| **N8** | Synthetic data | Realistic format and volume |
| **N9** | Individual ownership | Each member owns an area and presents it |

---

## 3. Corrections to our earlier drafts

The earlier docs (architecture plan, `TEAM_SPLIT.md`) were written before we had the catalogue. These points must change:

| Earlier draft said | Catalogue says | Action |
|---|---|---|
| 6-week timeline | Day 3 → Day 10 + 1 week (~2.5 weeks) | Re-plan the timeline once dates are confirmed (**Q15**) |
| Food-delivery domain | Brief is under **Technology** (product/platform systems) | Choose a Technology-style telemetry domain (see §4) |
| AI features inside the product (RAG, triage agent…) as core | Brief #31 **does not ask for AI inside the product**. The programme's "AI" is **how we build**: Claude Code, instruction files, skills, hooks, review log | Treat in-product AI as optional; make agent engineering a first-class deliverable (**Q14**) |
| No BRD, ADRs, CI gate, security or deployment work | All mandatory deliverables | Add to plan and to member ownership |
| Demo plan of our own design | Fixed 15-minute structure; every member presents | Align demo to the suggested split |
| Targets (85% coverage, 0.9 P/R) | Not stated anywhere | Remove until the panel confirms or we justify them (**Q16**) |

---

## 4. Domain candidates (pending the team's decision)

The brief is in the **Technology** industry. Wording like "client version stops emitting" points to **product telemetry from client apps**. These options fit; none is final.

| Option | Example events | Why it fits #31 |
|---|---|---|
| **A. SaaS product usage telemetry** (web + iOS + Android clients) | `page_view`, `feature_used`, `session_duration_ms`, `client_version`, `error_message` | Closest to the brief's wording; relevant to C5i's Technology clients; ties into brief #30 (usage early warning) |
| **B. Mobile app performance telemetry** | `app_start_ms`, `crash_log`, `os_version`, `client_version` | Classic telemetry; strong unit/nullable examples; crash logs are rich text |
| **C. API / platform service telemetry** | `latency_ms`, `status_code`, `endpoint`, `log_message`, `service_version` | Strong text payloads (logs); relevant to cloud/platform work |

---

## 5. Proposed approach (for discussion only; nothing frozen)

This is the shape we *expect* to build. It depends on the open questions.

```
      [Supplied pipeline — treated as read-only]
                         │
 ┌───────────────────────┼─────────────────────────────────┐
 │ 1. UNDERSTAND         │                                 │
 │   code graph → guarantees → characterisation tests      │
 ├─────────────────────────────────────────────────────────┤
 │ 2. HARDEN (inside a stated blast radius)                │
 │   hook points between stages → gates (schema, nulls,    │
 │   ranges, units, volume) → numeric drift → text drift   │
 │   → alerts with lineage to emitting source              │
 ├─────────────────────────────────────────────────────────┤
 │ 3. PROVE                                                │
 │   fault injection → precision / recall / lag vs baseline│
 │   → output equivalence → CI eval gate (blocks merges)   │
 ├─────────────────────────────────────────────────────────┤
 │ 4. OPERATE                                              │
 │   deploy (non-prod) → health checks → rollback → runbook│
 │   → dashboard (React) over Postgres results             │
 └─────────────────────────────────────────────────────────┘
   Engineered with Claude Code: CLAUDE.md, skills, hooks, review log
```

**Team preferences so far** (stack: Python / React / Postgres):
- Member C writes the pipeline and keeps it hidden. This depends on **Q1/Q2**.
- A general core that works on any pipeline, with style-specific adapters (Python, SQL). This depends on **Q17**.
- A batch pipeline replayed as micro-batches. This depends on **Q6**.

---

## 6. Open questions for the panel/mentor

Priority: 🔴 blocks design · 🟠 affects metrics/evaluation · 🟡 affects scope or effort

### A. The supplied pipeline
| # | P | Question | Why it matters | Our proposed default if the panel leaves it to us |
|---|---|---|---|---|
| **Q1** | 🔴 | Will the organisers **supply** the telemetry pipeline codebase (the brief says "supplied")? If yes, when, and in what language/style? | The whole design (code-graph adapters, hook points) depends on it | ✅ **Team decision (2026-09-29):** use an existing **open-source** pipeline so no member knows its code. Criteria in BRD §8a. |
| **Q2** | 🔴 | If not supplied: may a team member write it for the others, may we generate it with an AI agent, or must we use an existing open-source pipeline? | Honesty of "you did not write" | ✅ **Team decision (2026-09-29):** open source (see Q1) |
| **Q3** | 🟠 | Is there an **answer key** of the pipeline's true rules/guarantees to score our reconstruction against (as brief #03 has)? | Lets us score F3 objectively | The pipeline author writes a sealed key |
| **Q4** | 🟠 | What **baseline** should detection metrics be compared against: no checks, schema-only checks, or something else? | "Measured against a baseline" is mandatory | Both: no checks, and schema-only checks |

### B. Metric definitions
| # | P | Question | Why it matters | Proposed default |
|---|---|---|---|---|
| **Q5** | 🟠 | Is there a required list of degradation types, or do we define it? Must it include ones not named in the brief? | Defines the evaluation set | The brief's 3 (unit change, version stops emitting, new nullable) + type change, gradual drift, text changes, volume drop, and clean runs |
| **Q6** | 🟠 | Precision/recall per **alert** or per **injection**? Detection lag in **batches, events or seconds**? Is streaming expected, or is batch acceptable? | Changes how we score and what the pipeline must be | Per injection for recall, per alert for precision; lag in batches and seconds. ✅ **Team decision (2026-09-29):** event-driven, per batch on arrival (not per single event). Metric units still to confirm with the panel. |
| **Q7** | 🟠 | Characterisation-test coverage: **line, branch**, or **% of reconstructed guarantees covered**? | Different numbers, different effort | Report line + branch + guarantee coverage |
| **Q8** | 🟠 | "Equivalent output": **bit-exact**, or within a stated tolerance (floats, row order)? On clean data only? | Defines pass/fail of F11 | Exact on keys/counts, tolerance ≤1e-9 on floats, row order ignored, clean data |
| **Q9** | 🟠 | "Lineage back to the emitting source": what granularity is expected (client app, version, device, feed, batch, individual event)? How is completeness scored? | Defines F8 and the metric | client + version + batch + field + affected output |

### C. Scope
| # | P | Question | Why it matters | Proposed default |
|---|---|---|---|---|
| **Q10** | 🟡 | Any expected tool for the code graph, or is our choice fine (e.g. Python AST + networkx, or an agent-built graph)? | Tool choice | Our choice |
| **Q11** | 🟡 | "Gate" behaviour: should a failing batch be **blocked**, **quarantined** with the pipeline continuing, or is **observe-only** acceptable at first? | Affects equivalence and demo | Configurable: observe / enforce(quarantine) |
| **Q12** | 🟡 | "Text payloads": free-text fields (error messages, logs), JSON payload structure, or both? | Scope of F7 | Both |
| **Q13** | 🟡 | How should "controlled blast radius" be demonstrated: a diff limited to named files, CI rules, feature flags, or all of these? | Scope of F10 | Stated allowed paths + CI check + feature flag |
| **Q14** | 🟡 | Are AI features **inside** the product (e.g. LLM alert explanations, code-graph Q&A agent) expected or valued, or is the focus on building **with** agents? | Big scope decision | ✅ **Team decision (2026-09-29):** alert explainer only (BRD FR-12); AI explains, never decides. Still worth asking the panel if it is valued. |
| **Q17** | 🟡 | Is a pipeline-agnostic design (works on other pipelines via adapters) valued, or is one pipeline enough? | Effort vs "reusable asset" value | ✅ **Team decision (2026-09-29):** support **Python and SQL** pipelines at minimum |

### D. Programme logistics
| # | P | Question | Why it matters | Proposed default |
|---|---|---|---|---|
| **Q15** | ✅ | Exact dates: Day 3, Day 10, and the panel date? | Timeline | **Answered (team, 2026-09-28):** demo call on **8 Oct**. Timeline planning is set aside for now. |
| **Q16** | 🟠 | Are there **target values** for the metrics, or do we set and justify our own? | Acceptance criteria in the BRD | We set and justify them |
| **Q18** | 🟡 | Acceptable **non-production deployment target**: local Docker Compose, a cloud VM, or a specific platform? | Deployment effort | Docker Compose on a VM/local |
| **Q19** | 🟡 | CI platform expected (GitHub Actions? GitLab?) and repo hosting? | Where the CI eval gate lives | GitHub Actions |
| **Q20** | 🟡 | Expected **secrets manager** (cloud secrets manager, Vault, or GitHub Secrets acceptable)? | Security evidence | GitHub Secrets + `.env` excluded from agent context |
| **Q21** | 🟡 | Is a **Codex comparison** expected, or optional? | Extra work | Optional; skip unless asked |
| **Q22** | 🟡 | Expected **data volume** (events per batch/day) for "engineering decisions to be real"? | Generator and performance | ~1M events total, ~10k per batch |
| **Q23** | 🟡 | Can our team be **3** members (we are 3), and does the scoring expect one area per member? | Team split | 3 areas, one per member |

---

## 7. Team decisions still pending (internal, not for the panel)
1. Domain: option A, B or C in §4
2. Who owns which area. Redo `TEAM_SPLIT.md` after Q1, Q14 and Q15 are answered.
3. Repo hosting and naming
4. How we record agent review (review-log format)

## 8. Next steps
1. Send §6 (questions Q1–Q23) to the panel/mentor. **Q1, Q2 and Q15 first.**
2. Record answers here, marking each question ✅ answered, with the date and who answered.
3. Only then: freeze the BRD, then the design, then the task plan, then the team split.
