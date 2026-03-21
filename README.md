# Agent World Compiler PoC

A minimal proof-of-concept for deriving least-privilege boundaries for agent workflows from observed execution.

---

## What this is

This PoC does not try to make agent reasoning safe.
It makes the executable boundary around agent actions explicit, minimal, and reproducible.

This PoC is workflow-scoped: each manifest defines a least-privilege boundary for a specific agent workflow, not for the agent as a whole.

The central pattern is:

```
Observe → Profile → Manifest → Enforce
```

Execution traces are recorded from agent/tool activity. A profiler derives a minimal safe capability profile from observed benign behavior. A compiler turns that profile into a declarative manifest. A deterministic policy engine evaluates steps against that manifest.

---

## Problem statement

Agentic AI systems execute sequences of tool calls on behalf of a user or an automated pipeline. Each tool call touches a real resource — files, APIs, shells, credentials.

In most systems, the agent's *effective capability* is not defined in advance. It evolves opportunistically through:
- discovered tools,
- prompt instructions,
- runtime approvals.

Decisions are made at runtime, not from a predefined execution boundary.

This creates three concrete failure modes:

1. **Scope creep** – the agent accumulates capabilities beyond what any single workflow requires.
2. **Taint propagation** – data from an untrusted source flows into a side-effecting tool call without sanitisation.
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
   Running a trace through the profiler (`src/awc/compiler/profiler.py`) produces a minimal set of (tool, action, resource-prefix) triples from observed benign steps.

2. **That profile can be compiled into a manifest.**
   The manifest compiler (`src/awc/compiler/compile_manifest.py`) translates the profile into a human-readable, declarative YAML document.

3. **The compiled manifest produces reproducible decisions.**
   The enforcement engine (`src/awc/policy/engine.py`) takes any (step, manifest) pair and returns a deterministic `Decision` enum value.

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

The trace is the first concrete runtime artifact. Every downstream artifact — profile, manifest, decision — is derived from it.

---

## Bootstrap Trust Model

The system starts from a built-in mapping of input source types to trust levels. This mapping is the **bootstrap trust model** — a set of default assumptions the system applies before any step is evaluated.

```python
DEFAULT_INPUT_TRUST = {
    "repo_local":   "trusted",
    "environment":  "untrusted",
    "llm_output":   "untrusted",
    "tool_output":  "conditional",
}
```

This mapping is defined in `src/awc/policy/taint.py` and compiled into the manifest's `input_trust` block.

Key points:

- The user does **not** start by writing a trust model. The bootstrap trust model is the system's built-in starting point.
- These defaults reflect a conservative security posture: local repository content is trusted; LLM outputs and environment variables are not.
- The manifest's `input_trust` block can later be refined; the bootstrap defaults are the starting assumption, not the ceiling.
- Taint derivation uses this map as its source of truth for each step.

---

## Taint derivation and propagation

> Taint is a deterministic function of provenance and flow, not a manually assigned or heuristic label.

Taint is **derived** from the data lineage of each trace step and **propagated** through declared execution dependencies.

### How it works

1. Each step declares `input_sources` (e.g. `repo_local`, `environment`, `llm_output`).
2. The bootstrap trust model (embodied in `input_trust`) assigns a trust level to each source.
3. A step is **source-tainted** if any of its `input_sources` resolves to `untrusted` or `conditional`.
4. A step may declare `depends_on: [<step_id>, ...]`. If any dependency is tainted, the step inherits that taint (**propagation**).
5. Final taint = source taint OR propagated taint.

The enforcement engine then applies the core invariant:

> Tainted data cannot trigger an external side effect.

Taint derivation is implemented in `src/awc/policy/taint.py`. All reasons are auditable — every taint decision includes a label such as `untrusted_input:environment` or `depends_on_tainted:step-001`.

### What taint is not

Taint is not manually assigned. There is no `tainted: true` flag that a caller sets. Any such legacy annotation in a trace is explicitly ignored for policy decisions.

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

## Why observed execution matters

A World Manifest can be written by hand. An operator who understands the workflow can enumerate the allowed tools, actions, and resources upfront.

This PoC takes a different approach: derive the manifest from real execution.

The difference matters:

| Approach | Basis | Risk |
|---|---|---|
| Hand-written manifest | Opinion and assumption | May over-permit or under-permit based on what the author imagined |
| Derived manifest | Observed, benign execution | Grounded in actual behavior; narrower by construction |

The value is not just that a manifest exists — it is that the manifest can be derived from evidence rather than guessed.

Observed execution provides an empirical basis for workflow-specific capability boundaries. Design-time policy becomes reproducible and reviewable, and over-permissioning is reduced per workflow because the profile reflects what that specific workflow actually did — not what an agent might conceivably need across all tasks.

---

## Safe compression principle

The profiler and compiler may simplify or compress the observed behavior. For example, multiple resource URIs may be collapsed into a single prefix pattern.

One constraint is absolute:

> The manifest may compress observed behavior, but must never introduce capabilities not present in the safe trace.

Equivalently: you can lose precision, but you cannot add new capabilities.

In practice this means:
- tainted steps never widen the allowed set in the profile;
- the compiler only emits `allowed_actions` entries that correspond to tools and actions seen in the benign, untainted trace;
- the `denied_actions` list always includes a catch-all for undefined behavior.

---

## Example decisions

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

## Repository structure

```
.
├── src/awc/                        # library source code
│   ├── observe/
│   │   └── recorder.py             # Stage 0: record tool calls into traces
│   ├── compiler/
│   │   ├── profiler.py             # Stage 1: derive capability profile from traces
│   │   └── compile_manifest.py     # Stage 2: compile profile → World Manifest
│   └── policy/
│       ├── taint.py                # deterministic taint derivation & propagation
│       ├── engine.py               # Stage 3: enforcement engine
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
│   ├── record_and_compile.py       # stages 0–3 from TraceRecorder
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

- `TraceRecorder` — records agent tool calls into JSON traces (`src/awc/observe/recorder.py`)
- Trace schema with `tool`, `action`, `resource`, `input_sources`, `depends_on`
- **Provenance-derived taint** (`src/awc/policy/taint.py`)
  - source taint from `input_sources × input_trust`
  - propagated taint through `depends_on` execution graph
  - auditable reasons for every taint decision
- CapabilityProfile derivation — tainted steps (by provenance) never widen the allowed set
- World Manifest schema — declarative execution boundary with `input_trust` block
- Deterministic enforcement engine — provenance-aware, not annotation-driven
- Two trace fixtures (benign and unsafe, with `depends_on` dependency chains)
- CLI for trace evaluation
- Unit tests covering core invariants, taint derivation, and propagation
- Interactive Jupyter notebook walkthrough

### Current abstraction level

The PoC operates with a coarser capability model than the full long-term concept. The trace schema captures `(tool, action, resource)` structure, but the profiler and manifest compiler currently collapse some of this detail — for example, treating all `write` actions to a resource prefix equivalently rather than distinguishing finer-grained action semantics. This is a deliberate simplification for the PoC, not the conceptual ceiling.

---

## What is NOT implemented

- Live LLM integration
- Cryptographic attestation
- OS-level sandboxing
- Multi-agent trust models
- Live orchestration interception
- UI / dashboard
- Persistence layer

---

## Core invariants

1. **Determinism** – same manifest + same step → same decision
2. **Undefined = deny** – actions outside manifest are rejected
3. **Over-scoped = deny** – disallowed resources are blocked
4. **Taint safety** – tainted data cannot trigger external side effects; taint is derived from provenance and propagated through `depends_on`, not read from an annotation
5. **Approval gates** – sensitive actions surface explicitly
6. **Safe compression** – the manifest may compress observed behavior but must not introduce capabilities absent from the safe trace

---

## Manifest schema excerpt

```yaml
manifest_id: repo-safe-write
version: "1.0"

input_trust:
  repo_local: trusted
  environment: untrusted
  llm_output: untrusted
  tool_output: conditional

allowed_actions:
  - action: git_push
    permitted_resources: ["repo://remote/origin/*"]
    trust_required: trusted
    taint_ok: false

approval_required:
  - action: git_push
    resource_pattern: "repo://remote/*"
    reason: "All remote pushes require explicit operator approval."

denied_actions:
  - action: http_post
    reason: "Outbound HTTP calls not part of declared workflow."
  - action: env_read
    reason: "Environment variable access not part of declared workflow."

capability_constraints:
  taint_propagation: deny_external
  undefined_actions: deny
```

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

## Summit materials

Conference materials are in `docs/summit/`:

- `docs/summit/talk/conference_speech.md` — full spoken talk draft (10–15 min)
- `docs/summit/cfp/abstract.md` — CFP abstract
- `docs/summit/cfp/speaker_abstract.md` — short speaker summary
- `docs/summit/talk/outline.md` — talk structure
- `docs/summit/talk/qa-prep.md` — Q&A preparation
- `docs/summit/slides/` — slide outline and speaker notes

---

## License

MIT

---

## Citation

See [CITATION.cff](CITATION.cff).
