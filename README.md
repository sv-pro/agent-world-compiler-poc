# Agent World Compiler PoC

A minimal proof-of-concept for deriving least-privilege boundaries for agent workflows from observed execution.

Instead of exposing raw tools and filtering them at runtime, this PoC shows how **workflow-specific partial capabilities can be rendered as the only tools visible to the agent**.

---

## What this is

This PoC does not try to make agent reasoning safe.
It makes the executable boundary around agent actions **explicit, minimal, and reproducible**.

This PoC demonstrates boundary derivation and enforcement; rendered tools show how the same boundary can be projected into the agent's visible tool surface.

This PoC is **workflow-scoped**: each manifest defines a least-privilege boundary for a specific agent workflow, not for the agent as a whole.

The central pattern is:

```
Observe → Profile → Manifest → Render Tools → Enforce
```

Execution traces are recorded from agent/tool activity. A profiler derives a minimal safe capability profile from observed benign behavior. A compiler turns that profile into a declarative manifest.  

**That manifest is then projected into a narrowed, agent-facing tool surface.**

Instead of giving the agent broad, raw tools and checking usage after the fact, the system replaces them with **rendered partial capabilities** — constrained tools that encode only what the workflow is allowed to do.

> Capabilities are not only checked — they are rendered as the only tools the agent can see.

The PoC still demonstrates deterministic enforcement, but the key idea is stronger:

> The boundary can be enforced externally — or constructed as the executable world itself.

---

## Core idea: from tools to capabilities

Most agent systems expose tools like:

```yaml
tools:
  - git_push
  - http_post
  - env_read
```

and rely on runtime checks to decide whether a specific invocation is allowed.

This PoC demonstrates a different model:

```yaml
rendered_tools:
  - git_push_origin_only
  - git_commit_local
  - fs_read_repo_only
```

- Raw tools are **broad and ambient**
- Rendered tools are **narrow and workflow-scoped**

Forbidden capabilities are not denied — they are simply **absent**.

The agent does not operate over raw tools. It operates over rendered capabilities derived from the manifest.

> The agent does not choose what to do and get filtered.
> The agent can only act within what exists.

---

## Problem statement

Agentic AI systems execute sequences of tool calls on behalf of a user or an automated pipeline. Each tool call touches a real resource — files, APIs, shells, credentials.

In most systems, the agent's *effective capability* is not defined in advance. It evolves opportunistically through:

- discovered tools
- prompt instructions
- runtime approvals

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
   Running a trace through the profiler produces a minimal set of required capabilities from benign steps.

2. **That profile can be compiled into a manifest.**  
   The compiler translates the profile into a declarative YAML boundary.

3. **The manifest can both enforce and construct the boundary.**  
   It can:
   - deterministically evaluate actions (ALLOW / DENY / REQUIRE_APPROVAL)
   - and project itself into a **rendered tool surface** that replaces raw tools

---

## End-to-end flow

```
Observe → Profile → Manifest → Render Tools → Enforce → Decision
```

```
Trace
  ↓
Profiler (derive minimal capabilities)
  ↓
Manifest (declarative boundary)
  ↓
Render Tools (capability → tool projection)
  ↓
Enforcement (deterministic decisions)
```

### Critical transition

> The key transition is from raw tools to rendered partial capabilities.

---

## Bootstrap Trust Model

The system starts from a built-in mapping of input sources to trust levels:

```python
DEFAULT_INPUT_TRUST = {
    "repo_local":   "trusted",
    "environment":  "untrusted",
    "llm_output":   "untrusted",
    "tool_output":  "conditional",
}
```

- This is a system default, not user-authored
- It defines the initial provenance model
- It drives taint derivation

---

## Taint derivation and propagation

> Taint is a deterministic function of provenance and flow.

- derived from `input_sources`
- propagated via `depends_on`
- no manual flags
- fully auditable

Core invariant:

> Tainted data cannot trigger external side effects.

---

## Why observed execution matters

A manifest can be written manually — but that is guesswork.

This PoC derives it from real execution:

| Approach | Basis | Risk |
|---|---|---|
| Hand-written | Assumption | Over/under-permission |
| Derived | Observed behavior | Minimal by construction |

---

## Two Levels of Restriction

There are two distinct ways an action can be unavailable to the agent:

**Level 1 — Ontology (rendered tools):** The action does not exist in the agent's visible tool surface. It was never registered. The agent has no capability to invoke it. This is restriction by absence.

**Level 2 — Policy (enforcement):** The action exists as a raw tool, but the manifest does not permit it. The agent attempts to invoke it; the engine evaluates the step and returns `DENY`.

Example:

```
git_push → DENY (tool not registered)   ← ontology: does not exist in rendered surface
http_post → DENY (tainted)              ← policy: exists, but denied by enforcement
```

These are not the same restriction. "Not available" and "available but denied" are distinct concepts with different enforcement mechanisms.

> Some actions do not exist.
> Others exist, but are not allowed.

---

## Why rendered tools matter

Policies alone are external.

Rendered tools make the boundary part of the execution model:

- Raw tools → ambient capability
- Policy → external filter
- Rendered tools → **constructed execution world**

Rendered tools are not a convenience layer; they are a projection of the same boundary enforced by the policy engine.

> Instead of filtering behavior, we define what behavior can exist.

---

## Safe compression principle

> You can lose precision, but you cannot add new capabilities.

- profiles may compress traces
- manifests may generalize patterns
- but no new capability may be introduced

---

## Example decisions

### Allowed

```yaml
git_commit → ALLOW
```

### Denied (tainted input)

```yaml
http_post → DENY (tainted)
```

### Denied (explicitly denied action)

```yaml
env_read → DENY (explicitly denied: not in declared workflow)
```

### Denied (undefined — not registered)

```yaml
git_push → DENY (tool not registered)
```

This last case is distinct: the action is not in `allowed_actions` and was never registered. It does not exist in the compiled boundary. Undefined = deny.

---

## What is implemented

- Trace recording
- Provenance-based taint derivation
- Capability profile extraction
- Manifest compilation
- Rendered tool projection
- Deterministic enforcement engine
- End-to-end demo + tests

---

## What is NOT implemented

- LLM integration
- Runtime tool interception
- MCP server
- UI
- Multi-agent trust
- OS sandboxing

---

## Core invariants

1. Determinism  
2. Undefined = deny  
3. Over-scoped = deny  
4. Taint safety  
5. Approval surfaced  
6. Safe compression  

---

## Key takeaway

> This PoC does not try to detect unsafe behavior.  
> It shows how to construct a world where unsafe behavior is not executable.

---

## Quickstart

```bash
pip install -e ".[dev]"
make demo
make test
```

---

## License

MIT