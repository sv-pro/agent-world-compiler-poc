# Fixtures

Data artifacts that flow through the compiler pipeline. Each subdirectory
corresponds to a stage in the pipeline and has a clear lifecycle:

```
traces/  →  profiles/  →  manifests/
(input)     (derived)     (compiled)
```

## traces/

Recorded agent execution traces (JSON). These are the raw input to the
pipeline — immutable observations of tool calls, resources accessed, and
taint status.

## profiles/

Capability profiles (YAML) derived from traces by the profiler. A profile
is the minimal set of (tool, action, resource-prefix) triples observed
across all non-tainted trace steps.

## manifests/

Compiled World Manifests (YAML) — the declarative policy artifact consumed
by the enforcement engine. A manifest defines allowed actions, denied
actions, approval gates, trust requirements, and capability constraints.
