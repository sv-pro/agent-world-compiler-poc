# Agent World Compiler PoC

A minimal proof-of-concept for deriving least-privilege boundaries for agent workflows from observed execution.

Instead of exposing raw tools and filtering them at runtime, this system derives workflow-specific capabilities and renders them as the only tools visible to the agent.

---

## What this is

This PoC does not try to make agent reasoning safe.

It makes the executable boundary around agent actions:
- explicit
- minimal
- reproducible

Each manifest defines a least-privilege boundary for a specific workflow — not for the agent as a whole.

---

## Architectural framing

Traditional agent systems operate in an open world:

- tools exist
- policies decide what is allowed

This is reactive:
the agent can attempt any action, and the system must filter it.

This PoC explores a different model.

We derive a boundary and construct the execution world from it.

> We do not restrict tools.  
> We construct the only tools that exist.

---

## Core idea: from tools to capabilities

Most systems:

```yaml
tools:
  - git_push
  - http_post
  - env_read
```

This PoC:

```yaml
rendered_tools:
  - git_push_origin_only
  - git_commit_local
  - fs_read_repo_only
```

- raw tools → ambient authority  
- rendered tools → scoped capability  

Forbidden capabilities are not denied — they are absent.

---

## Execution model

```
Observe → Profile → Manifest → Render → Enforce
```

```
Trace
  ↓
Profiler (derive minimal capability set)
  ↓
Manifest (declarative boundary)
  ↓
Render (capability → tool projection)
  ↓
Enforcement (deterministic decision)
```

---

## Two levels of restriction

### 1. Ontology (constructed world)

The capability does not exist.

```
git_push → DENY (tool not registered)
```

The agent cannot invoke it.

---

### 2. Policy (enforced boundary)

The capability exists, but is denied.

```
http_post → DENY (tainted)
```

---

> Some actions do not exist.  
> Others exist, but are not allowed.

---

## Taint model

Taint is derived from provenance:

- input_sources
- depends_on

No manual flags.

```
repo_local   → trusted
environment  → untrusted
llm_output   → untrusted
tool_output  → conditional
```

Core invariant:

> Tainted data cannot trigger external side effects.

---

## Why observed execution

Manual policy = guess  
Derived policy = evidence

| Approach | Risk |
|--------|------|
| Hand-written | Over/under-permission |
| Derived | Minimal by construction |

---

## Safe compression

> You can lose precision, but you cannot add capabilities.

---

## Example decisions

```
git_commit → ALLOW
http_post → DENY (tainted)
env_read → DENY (explicitly denied)
git_push → DENY (tool not registered)
```

---

## What is implemented

- trace recording
- taint derivation
- capability profile
- manifest compiler
- rendered tools
- deterministic engine

---

## What is NOT implemented

- runtime interception
- UI
- MCP
- sandboxing
- multi-agent trust

---

## Key takeaway

This PoC does not try to detect unsafe behavior.

It constructs a world where unsafe behavior cannot be expressed.