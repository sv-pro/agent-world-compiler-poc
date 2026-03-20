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

## End-to-end flow

```
Observe → Profile → Manifest → Enforce → Decision
```

```
fixtures/traces/*.json
        ↓
src/awc/compiler/profiler.py
        ↓
src/awc/compiler/compile_manifest.py
        ↓
src/awc/policy/engine.py
        ↓
ALLOW | DENY | REQUIRE_APPROVAL
```

---

## Example

### Allowed action

```yaml
step:
  tool: git
  action: commit
  resource: repo://current
  tainted: false

decision:
  result: ALLOW
```

### Denied action (tainted external)

```yaml
step:
  tool: http
  action: post
  resource: https://external.example/api
  tainted: true

decision:
  result: DENY
  reason: tainted_external_side_effect
```

---

## Why this matters

- Reduces capability scope creep by deriving minimal execution surfaces
- Converts runtime decisions into reproducible artifacts
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
│       ├── engine.py               # deterministic enforcement engine
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
├── Makefile
└── requirements.txt
```

---

## What is implemented

- Trace schema with `tool`, `action`, `resource`, `input_sources`, `tainted`
- CapabilityProfile derivation (tainted steps never widen scope)
- World Manifest schema (declarative execution boundary)
- Deterministic enforcement engine
- Two trace fixtures (benign + unsafe)
- CLI for evaluation
- Unit tests covering core invariants
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
