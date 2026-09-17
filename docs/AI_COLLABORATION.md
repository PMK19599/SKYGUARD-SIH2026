# Team Axiom Forge — AI Collaboration Guidelines

## Multi-Agent & Multi-Contributor Principles

In Team Axiom Forge, different contributors and developers may collaborate using different AI coding assistants (e.g., Gemini / Antigravity, Claude Code, GitHub Copilot, Devin, Cursor).

To maintain absolute architectural coherence, data contract stability, and safety alignment, all human contributors and AI assistants **must** adhere strictly to the rules in this document.

---

## Mandatory Reading Before Modifying Code

Before proposing or generating any modifications to core architecture or data models, every contributor and AI agent must review:

1. [`README.md`](../README.md) — Mission, safety principle, positioning, and boundaries.
2. [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — Ingestion-to-decision pipeline, architectural invariants, and Scenario Lab rules.
3. [`docs/DATA_CONTRACT.md`](DATA_CONTRACT.md) — Canonical Observation, Station, Evidence, Decision, and API schemas.
4. [`docs/DECISION_STATES.md`](DECISION_STATES.md) — The five operational states (`NORMAL`, `WORLD`, `SENSOR`, `BOTH`, `UNKNOWN`) and required actions.

> [!WARNING]
> **Strict Non-Negotiable**:
> Contributors and AI assistants **must NOT** silently change or alter the five-state taxonomy (`NORMAL`, `WORLD`, `SENSOR`, `BOTH`, `UNKNOWN`) or modify canonical contract schema field names without explicit team-wide consensus.

---

## Architectural Invariants (Must Be Upheld by All AI Agents)

1. **Observation ≠ Interpretation**: Raw observations are immutable physical facts; zero diagnosis or state fields permitted in observations.
2. **Evidence ≠ Decision**: Evidence supports or contradicts a hypothesis; evidence never directly assigns operational state.
3. **AI ≠ Judge**: AI models provide supporting hypotheses; the deterministic decision engine holds final authority.
4. **Outlier ≠ Fault**: Extreme measurements can be meteorological events (`WORLD`), sensor faults (`SENSOR`), or both.
5. **Agreement ≠ Independence**: Corroborating sources must be structurally independent; mere agreement is insufficient.
6. **Correlation ≠ Independence**: Cross-sensor or spatial correlation does not guarantee independent evidence channels.
7. **`BOTH` Requires Independent Support**: `BOTH` strictly requires independent evidence corroborating both an environmental event and a sensor issue.
8. **`UNKNOWN` is Deliberate**: When evidence is missing, conflicting, stale, or non-independent, `UNKNOWN` is the correct safety outcome.
9. **Dashboard Never Diagnoses**: Dashboard is strictly an observational and presentation layer.
10. **Scenario Labels Never Enter Decision Logic**: Scenario metadata is validation-only and must never reach runtime decision logic.

---

## Standardized Evidence Labels

All evidence collectors, physical heuristics, and ML models must output supporting evidence tagged with one of four standardized evidence labels:

| Evidence Label | Definition | Usage Context |
|---|---|---|
| **`SUPPORTED`** | Hypothesis is directly corroborated by high-quality, independent data. | e.g. 3 independent neighbor stations show identical rapid pressure surge. |
| **`QUALIFIED`** | Evidence supports the hypothesis with known caveats (e.g., high noise, moderate latency). | e.g. Observation supports event but neighboring station data is 15 minutes old. |
| **`UNKNOWN`** | Evidence is ambiguous, conflicting, or non-independent. | e.g. Neighbors disagree or all available sensors share a single electrical bus. |
| **`REJECTED`** | Evidence actively refutes the hypothesis. | e.g. An isolated station shows a 15°C spike while 4 surrounding stations report calm 22°C. |

---

## Suggested Workstreams

To prevent merge conflicts and maintain modularity, development is partitioned into distinct decoupled workstreams:

1. **`backend/` (Decision Engine & Ingestion API)**
   - Deterministic bounds checking, evidence fusion, independence gating, and operational state assignment.
2. **`frontend/` (Command-Center Dashboard)**
   - Visualization of decisions, evidence cards, station maps, and time series (strictly read-only / non-diagnostic).
3. **`ml/` (Contextual Evidence Generation)**
   - Temporal and spatial ML models providing `SUPPORTED`/`QUALIFIED`/`UNKNOWN`/`REJECTED` hypotheses.
4. **`simulator/` (Virtual AWS Network & Scenario Injection)**
   - Synthetic multi-station environmental simulation with reproducible fault and storm scenarios.
5. **`edge/` (ESP32 + BME280 Edge Testbed)**
   - Embedded firmware and serial ingestion adapter for physical testbed validation.
6. **`tests/` & `docs/` (Validation, Documentation & Demo Runbooks)**
   - Automated contract tests, benchmark validation suites, and demo flows.

---

## Claims & Benchmarking Ethics

- **Never turn synthetic benchmark scores into production claims.**
- All benchmark metrics must be explicitly cited as *"Evaluated on synthetic AWS scenario suite v1"* rather than claiming *"99% real-world accuracy"*.
- Acknowledge limitations transparently: edge hardware is an acquisition demonstration testbed, not an operational field-hardened meteorological station.
