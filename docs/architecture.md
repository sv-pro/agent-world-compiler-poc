# Architecture

The Agent World Compiler PoC is structured as a linear pipeline with five
named stages.  Each stage has a clear input and a clear output.

## End-to-end pipeline

```mermaid
flowchart TD
    A["Agent tool calls\n(observed execution)"] -->|"raw events"| B

    subgraph Observe["Stage 0 – Record"]
        B["TraceRecorder\n(src/awc/observe/recorder.py)"]
    end

    B -->|"trace JSON\n(step list)"| C

    subgraph Profile["Stage 1 – Profile"]
        C["Capability Profile Derivation\n(src/awc/compiler/profiler.py)"]
    end

    C -->|"allowed tools / actions /\nresources (YAML)"| D

    subgraph Compile["Stage 2 – Compile"]
        D["World Manifest Compiler\n(src/awc/compiler/compile_manifest.py)"]
    end

    D -->|"declarative manifest\n(YAML)"| E

    subgraph Enforce["Stage 3 – Enforce"]
        E["Enforcement Engine\n(src/awc/policy/engine.py)"]
    end

    E -->|"decision"| F

    subgraph Output["Decision Output"]
        F{{"ALLOW\nDENY\nREQUIRE_APPROVAL"}}
    end

    style Observe  fill:#f1f8e9,stroke:#558b2f
    style Profile  fill:#e8f5e9,stroke:#388e3c
    style Compile  fill:#e3f2fd,stroke:#1976d2
    style Enforce  fill:#fff3e0,stroke:#f57c00
    style Output   fill:#fce4ec,stroke:#c62828
```

## Component responsibilities

| Component | File(s) | Role |
| --- | --- | --- |
| **TraceRecorder** | `src/awc/observe/recorder.py` | Stage 0 — records agent tool calls into a trace JSON file.  The fixtures in `fixtures/traces/` are the saved output of a recorder. |
| Trace fixtures | `fixtures/traces/*.json` | Immutable, recorded observations of agent/tool execution. |
| Profiler | `src/awc/compiler/profiler.py` | Derives a `CapabilityProfile` from one or more traces.  Tainted steps are counted but never widen the allowed set. |
| Manifest compiler | `src/awc/compiler/compile_manifest.py` | Translates a `CapabilityProfile` into a structured YAML manifest. |
| Enforcement engine | `src/awc/policy/engine.py` | Evaluates a single trace step against a manifest and returns a deterministic `Decision`. |
| CLI wrapper | `src/awc/policy/evaluate.py` | Iterates all steps of a trace and prints a decision table. |
| Demo runner | `examples/demo_pipeline.py` | Executes the full pipeline from fixtures and prints a human-readable summary. |
| Record + compile demo | `examples/record_and_compile.py` | Shows the full pipeline starting from `TraceRecorder` — no fixture files needed. |

## Data model

```text
Trace (JSON)
  └── steps[]
        ├── tool          (string)
        ├── action        (string)
        ├── resource      (URI string)
        ├── input_sources (list[string])
        └── depends_on    (list[string])

CapabilityProfile (Python dataclass / YAML)
  ├── allowed_tools     (set)
  ├── allowed_actions   (set)
  └── allowed_resources (set of URI prefixes)

WorldManifest (YAML)
  ├── allowed_actions[]
  │     ├── action
  │     ├── permitted_resources[]
  │     ├── trust_required
  │     └── taint_ok
  ├── approval_required[]
  ├── denied_actions[]
  ├── input_trust{}
  ├── capability_constraints{}
  └── provenance{}
```

## Decision rules (priority order)

1. **Taint + external** → `DENY`
2. **Explicitly denied action** → `DENY`
3. **Action not in allowed set** → `DENY` *(undefined = deny)*
4. **Resource outside permitted patterns** → `DENY`
5. **Input trust below required** → `DENY`
6. **Matches approval_required** → `REQUIRE_APPROVAL`
7. **Otherwise** → `ALLOW`
