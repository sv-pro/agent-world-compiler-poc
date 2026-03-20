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
   Running a trace through the profiler (`compiler/profiler.py`) produces a minimal set of (tool, action, resource-prefix) triples.

2. **That profile can be compiled into a manifest.**  
   The manifest compiler (`compiler/compile_manifest.py`) translates the profile into a human-readable, declarative YAML document.

3. **The compiled manifest produces reproducible decisions.**  
   The enforcement engine (`policy/engine.py`) takes any (step, manifest) pair and returns a deterministic `Decision` enum value.

---

## End-to-end flow

```
Observe → Profile → Manifest → Enforce → Decision
```

```
traces/*.json
      ↓
compiler/profiler.py
      ↓
compiler/compile_manifest.py
      ↓
policy/engine.py
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
├── compiler/
│   ├── profiler.py
│   └── compile_manifest.py
├── demo/
│   └── run.py
├── docs/
│   └── architecture.md
├── examples/
├── manifests/
│   └── repo-safe-write.yaml
├── policy/
│   ├── engine.py
│   └── evaluate.py
├── profiles/
│   └── repo_safe_write.yaml
├── tests/
├── traces/
│   ├── benign_repo_maintenance.json
│   └── unsafe_exfiltration.json
├── pyproject.toml
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
5. **Explicit approval** – risky actions are surfaced, not hidden  

---

## Manifest schema (excerpt)

```yaml
manifest_id: string
version: string

input_trust:
  source_name: trusted|conditional|untrusted

allowed_actions:
  - action: string
    permitted_resources: list
    trust_required: level
    taint_ok: bool

approval_required:
  - action: string
    resource_pattern: glob
    reason: string

denied_actions:
  - action: string
    reason: string

capability_constraints:
  taint_propagation: deny_external
  allow_network_calls: bool
  allow_env_secrets: bool
  undefined_actions: deny
```

---

## Summit materials

See `summit/README.md` for CFP drafts, demo plan, and diagrams.

---

## License

MIT