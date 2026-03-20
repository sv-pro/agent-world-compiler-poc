# Agent World Compiler PoC

A minimal proof-of-concept showing how observed agent execution can be compiled into deterministic least-privilege runtime boundaries.

---

## What this is

This PoC does not try to make agent reasoning safe.
It makes the executable boundary around agent actions explicit, minimal, and reproducible.

---

## Problem statement

Agentic AI systems execute sequences of tool calls on behalf of a user or an automated pipeline. Each tool call touches a real resource (files, APIs, shells, credentials).

In most systems, the agent's *effective capability* is not defined in advance. It evolves opportunistically through:
- discovered tools,
- prompt instructions,
- runtime approvals.

Decisions are made at runtime, not from a predefined execution boundary.

This creates three concrete failure modes:

1. **Scope creep** – the agent accumulates capabilities beyond what any single workflow requires.
2. **Taint propagation** – data from an untrusted source (LLM output, external API response) flows into a side-effecting tool call without sanitisation.
3. **Undefined behaviour** – the agent invokes a tool or action outside the intended workflow surface, with no predefined boundary to constrain it.

---

## Threat model

| Asset | Threat | Example |
|---|---|---|
| Local repository | Unauthorised remote push | Agent pushes to a fork instead of `origin` |
| Secrets / env vars | Exfiltration via outbound call | Agent reads `SECRET_TOKEN`, posts it to an external URL |
| Shell | Prompt-injection command execution | LLM-constructed shell command runs as the agent's user |
| Trust boundary | Confused deputy | Agent uses a trusted credential to act on an untrusted instruction |

Out of scope for this PoC:
- multi-agent trust
- cryptographic attestation
- OS-level sandboxing

---

## PoC hypothesis

Three claims are tested:

1. **Observed execution can be distilled into a capability profile.**
   Running a trace through the profiler (`src/awc/compiler/profiler.py`) produces a minimal set of (tool, action, resource-prefix) triples.

2. **That profile can be compiled into a manifest.**
   The manifest compiler (`src/awc/compiler/compile_manifest.py`) translates the profile into a human-readable, declarative YAML document.

3. **The compiled manifest produces reproducible decisions.**
   The enforcement engine (`src/awc/policy/engine.py`) takes any (step, manifest) pair and returns a deterministic `Decision` enum value.

---

## Taint model

> Taint is a deterministic function of provenance and flow, not a manually assigned or heuristic label.

Taint is **derived** from the data lineage of each trace step and **propagated** through declared execution dependencies.

### How it works

1. Each step declares `input_sources` (e.g. `repo_local`, `environment`, `llm_output`).
2. The manifest's `input_trust` map assigns a trust level to each source:
   - `trusted` – e.g. `repo_local`
   - `conditional` – e.g. `tool_output`
   - `untrusted` – e.g. `environment`, `llm_output`
3. A step is **source-tainted** if any of its `input_sources` resolves to `untrusted` (or `conditional`).
4. A step may declare `depends_on: [<step_id>, ...]`. If any dependency is tainted, the step inherits that taint (**propagation**).
5. Final taint = source taint OR propagated taint.

The enforcement engine then applies the core invariant:

> Tainted data cannot trigger an external side effect.

### What this replaces

The old model read a `tainted: true/false` annotation directly from the trace. That annotation is now **legacy noise** — it is ignored for policy decisions. If present in a trace fixture, it has no effect on enforcement.

### Step schema

```json
{
  "step_id": "step-002",
  "tool": "http_post",
  "action": "network_call",
  "resource": "https://external.example/api",
  "input_sources": ["environment"],
  "depends_on": ["step-001"],
  "metadata": {}
}
```

- `input_sources` – required; drives trust and source-taint derivation
- `depends_on` – optional; enables taint propagation through the execution graph

---

## End-to-end flow

```
Observe → Profile → Manifest → Enforce → Decision
```

```
fixtures/traces/*.json
        ↓
src/awc/compiler/profiler.py      (derive_profile: taint from provenance)
        ↓
src/awc/compiler/compile_manifest.py
        ↓
src/awc/policy/taint.py           (compute_trace_taint: derive + propagate)
        ↓
src/awc/policy/engine.py          (evaluate_step: provenance-aware decisions)
        ↓
ALLOW | DENY | REQUIRE_APPROVAL
```

---

## Example

### Allowed action (trusted provenance)

```yaml
step:
  tool: git_commit
  action: write
  resource: repo://local/commits
  input_sources: [repo_local]   # trusted

decision:
  result: ALLOW
```

### Denied (tainted source → external resource)

```yaml
step:
  tool: http_post
  action: network_call
  resource: https://external.example/api
  input_sources: [environment]  # untrusted → derived taint = true

decision:
  result: DENY
  reason: "Tainted data cannot trigger external resource (taint derived from: untrusted_input:environment)."
```

### Denied via propagation (trusted source, tainted dependency)

```yaml
step:
  tool: http_post
  action: network_call
  resource: https://external.example/api
  input_sources: [repo_local]   # trusted by source
  depends_on: [step-001]        # step-001 read from environment (tainted)

decision:
  result: DENY
  reason: "Tainted data cannot trigger external resource (taint derived from: depends_on_tainted:step-001)."
```

---

## Why this matters

- Reduces capability scope creep by deriving minimal execution surfaces
- Converts runtime decisions into reproducible artifacts
- Makes taint auditable and explainable, not guessed
- Makes approval boundaries explicit and reviewable

---

## Repository structure

```
.
├── src/awc/                        # library source code
│   ├── compiler/
│   │   ├── profiler.py             # derive capability profile from traces
│   │   └── compile_manifest.py     # compile profile → World Manifest
│   └── policy/
│       ├── taint.py                # deterministic taint derivation & propagation
│       ├── engine.py               # provenance-aware enforcement engine
│       └── evaluate.py             # CLI trace evaluator
│
├── fixtures/                       # data artifacts (pipeline I/O)
│   ├── traces/                     # recorded agent execution traces
│   │   ├── benign_repo_maintenance.json
│   │   └── unsafe_exfiltration.json
│   ├── profiles/                   # derived capability profiles
│   │   └── repo_safe_write.yaml
│   └── manifests/                  # compiled world manifests
│       └── repo-safe-write.yaml
│
├── tests/                          # pytest test suite
│   ├── test_taint.py               # taint derivation & propagation unit tests
│   ├── test_compiler.py            # profiler + manifest compiler tests
│   ├── test_engine.py              # enforcement engine unit tests
│   └── test_integration.py         # end-to-end pipeline tests
│
├── examples/                       # runnable examples and demos
│   ├── demo_pipeline.py            # full four-stage demo
│   ├── derive_and_compile.py       # compiler pipeline example
│   └── evaluate_example.py         # engine usage example
│
├── notebooks/                      # interactive Jupyter notebooks
│   └── pipeline_walkthrough.ipynb  # step-by-step pipeline demo
│
├── docs/                           # documentation
│   ├── architecture.md             # architecture and data model
│   └── summit/                     # conference talk materials
│
├── pyproject.toml
└── requirements.txt
```

---

## What is implemented

- Trace schema with `tool`, `action`, `resource`, `input_sources`, `depends_on`
- **Provenance-derived taint** (`src/awc/policy/taint.py`)
  - source taint from `input_sources × input_trust`
  - propagated taint through `depends_on` execution graph
  - auditable reasons for every taint decision
- CapabilityProfile derivation (tainted steps — by provenance — never widen scope)
- World Manifest schema (declarative execution boundary with `input_trust`)
- Deterministic enforcement engine (provenance-aware, not annotation-driven)
- Two trace fixtures (benign + unsafe, with `depends_on` dependency chains)
- CLI for evaluation
- Unit tests covering core invariants including taint derivation and propagation
- Interactive Jupyter notebook walkthrough

---

## What is NOT implemented

- Live LLM integration
- Cryptographic attestation
- OS-level sandboxing
- Multi-agent trust models
- UI / dashboard
- Persistence layer

---

## Core invariants

1. **Determinism** – same manifest + same step → same decision
2. **Undefined = deny** – actions outside manifest are rejected
3. **Over-scoped = deny** – disallowed resources are blocked
4. **Taint safety** – tainted data cannot trigger external side effects
   Taint is derived from provenance and propagated through `depends_on`, not read from an annotation.
5. **Approval gates** – sensitive actions surface explicitly

---

## Quickstart

```bash
# Install
pip install -e ".[dev]"

# Interactive notebook
jupyter notebook notebooks/pipeline_walkthrough.ipynb

# Run demo
make demo

# Run tests
make test

# Evaluate traces
make evaluate-benign
make evaluate-unsafe

# Recompile manifest from profile
make compile
```

---

## License

MIT

---

## Citation

See [CITATION.cff](CITATION.cff).
