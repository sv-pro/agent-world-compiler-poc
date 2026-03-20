# Agent World Compiler PoC

A minimal proof-of-concept for a conference talk about securing agentic AI by
converting observed agent execution into least-privilege runtime boundaries.

---

## Problem statement

Agentic AI systems execute sequences of tool calls on behalf of a user or an
automated pipeline.  Each tool call touches a real resource (files, APIs,
shells, credentials).  The agent's *effective capability* at runtime is rarely
defined in advance; it expands opportunistically as the agent discovers new
tools or receives instructions from untrusted sources.

This creates three concrete failure modes:

1. **Scope creep** – the agent accumulates capabilities beyond what any single
   workflow requires.
2. **Taint propagation** – data from an untrusted source (LLM output, external
   API response) flows into a side-effecting tool call without sanitisation.
3. **Undefined behaviour** – the agent invokes a tool that was never part of
   the intended workflow and there is no policy to deny it.

---

## Threat model

| Asset | Threat | Example |
|---|---|---|
| Local repository | Unauthorised remote push | Agent pushes to a fork instead of `origin` |
| Secrets / env vars | Exfiltration via outbound call | Agent reads `SECRET_TOKEN`, posts it to an external URL |
| Shell | Prompt-injection command execution | LLM-constructed shell command runs as the agent's user |
| Trust boundary | Confused deputy | Agent uses a trusted credential to act on an untrusted instruction |

Out of scope for this PoC: multi-agent trust, cryptographic attestation, and
runtime sandboxing at the OS level.

---

## PoC hypothesis

Three claims are tested:

1. **Observed execution can be reduced to a capability profile.**  
   Running a trace through the profiler (`compiler/profiler.py`) produces a
   minimal set of (tool, action, resource-prefix) triples.

2. **That profile can be compiled into a manifest.**  
   The manifest compiler (`compiler/compile_manifest.py`) translates the
   profile into a human-readable, declarative YAML document.

3. **The compiled manifest produces reproducible allow/deny/require-approval
   decisions.**  
   The enforcement engine (`policy/engine.py`) takes any (step, manifest) pair
   and returns a deterministic `Decision` enum value.

---

## End-to-end flow

```
Observe → Profile → Manifest → Enforce
```

```
traces/*.json          ← recorded agent execution (fixture files)
      ↓
compiler/profiler.py   ← derive CapabilityProfile (allowed tools / actions / resources)
      ↓
compiler/compile_manifest.py  ← compile into a World Manifest (YAML)
      ↓
policy/engine.py       ← evaluate each trace step → ALLOW | DENY | REQUIRE_APPROVAL
```

See [`docs/architecture.md`](docs/architecture.md) for the full Mermaid diagram.

---

## Repository structure

```
.
├── compiler/               # Profile derivation and manifest compilation
│   ├── profiler.py         # derive_profile(): trace → CapabilityProfile
│   └── compile_manifest.py # compile_manifest(): profile → World Manifest dict
├── demo/
│   └── run.py              # End-to-end demo runner
├── docs/
│   └── architecture.md     # Mermaid architecture diagram
├── examples/               # Short standalone usage examples
├── manifests/
│   └── repo-safe-write.yaml  # Compiled manifest for the benign workflow
├── policy/
│   ├── engine.py           # Core enforcement engine
│   └── evaluate.py         # CLI: evaluate a trace against a manifest
├── profiles/
│   └── repo_safe_write.yaml  # Derived capability profile
├── tests/
│   ├── conftest.py
│   ├── test_engine.py      # Unit tests for the enforcement engine
│   ├── test_compiler.py    # Unit tests for profiler and compiler
│   └── test_integration.py # End-to-end pipeline tests
├── traces/
│   ├── benign_repo_maintenance.json
│   └── unsafe_exfiltration.json
├── CITATION.cff
├── CONTRIBUTING.md
├── LICENSE
├── Makefile
├── pyproject.toml
└── requirements.txt
```

---

## What is implemented

- Trace schema (JSON) with `tool`, `action`, `resource`, `input_sources`, `tainted` per step.
- `CapabilityProfile` derivation: tainted steps are counted but never widen the allowed set.
- World Manifest schema: `allowed_actions`, `approval_required`, `denied_actions`,
  `input_trust`, `capability_constraints`, `provenance`.
- Deterministic enforcement engine with seven prioritised decision rules.
- Two fixture traces: benign repo maintenance and unsafe exfiltration attempt.
- One static manifest: `repo-safe-write`.
- CLI: `python -m policy.evaluate --trace … --manifest …`
- pytest suite proving all five invariants (determinism, undefined=deny, over-scoped=deny,
  taint=deny-external, approval surfaced).

## What is NOT implemented

- Live LLM integration or real agent orchestration.
- Cryptographic trace signing or attestation.
- OS-level sandboxing (seccomp, cgroups).
- Multi-agent or multi-principal trust hierarchies.
- A web UI or dashboard.
- Persistence / database.

---

## Setup

**Requirements:** Python 3.12+

```bash
git clone https://github.com/sv-pro/agent-world-compiler-poc.git
cd agent-world-compiler-poc
pip install -e ".[dev]"
```

---

## Running the demo

```bash
make demo
# or
python -m demo.run
```

The demo runs all four stages in sequence and prints a decision table for both
the benign and the unsafe trace.

---

## Running individual commands

```bash
# Derive a profile from a trace
python -m compiler.profiler traces/benign_repo_maintenance.json

# Compile a manifest from a profile
python -m compiler.compile_manifest profiles/repo_safe_write.yaml

# Evaluate a trace against a manifest
python -m policy.evaluate \
    --trace traces/benign_repo_maintenance.json \
    --manifest manifests/repo-safe-write.yaml

python -m policy.evaluate \
    --trace traces/unsafe_exfiltration.json \
    --manifest manifests/repo-safe-write.yaml

# JSON output
python -m policy.evaluate --json \
    --trace traces/unsafe_exfiltration.json \
    --manifest manifests/repo-safe-write.yaml
```

---

## Running tests

```bash
pytest
# or
make test
```

The test suite asserts five invariants:

1. **Determinism** – same manifest + same step → same decision, every time.
2. **Undefined actions denied** – any action not in `allowed_actions` → `DENY`.
3. **Over-scoped actions denied** – HTTP calls, env reads, and pushes to
   unauthorised remotes → `DENY`.
4. **Tainted data cannot trigger external side effects** – tainted + external
   resource → `DENY`.
5. **Approval surfaced** – remote pushes → `REQUIRE_APPROVAL`.

---

## Manifest schema reference

```yaml
manifest_id:       string
version:           string
description:       string
provenance:
  author:          string
  created:         date
  source_profile:  path
  source_traces:   list[path]
input_trust:       map[source_name → trusted|conditional|untrusted]
allowed_actions:
  - action:              string
    permitted_resources: list[glob-pattern]
    trust_required:      trusted|conditional|untrusted
    taint_ok:            bool
approval_required:
  - action:            string
    resource_pattern:  glob-pattern
    reason:            string
denied_actions:
  - action: string
    reason: string
capability_constraints:
  taint_propagation:  deny_external
  max_scope:          string
  allow_network_calls: bool
  allow_env_secrets:   bool
  undefined_actions:   deny
```

## Summit materials

This repository includes conference-supporting materials for a proposed OWASP GenAI & Agentic Security summit talk.

See [summit/README.md](summit/README.md) for CFP drafts, talk outline, demo plan, diagrams, and speaker notes.

---

## License

MIT – see [LICENSE](LICENSE).

## Citation

See [CITATION.cff](CITATION.cff).
