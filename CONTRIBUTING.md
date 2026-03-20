# Contributing to Agent World Compiler PoC

This is a research-grade engineering demo intended to support a conference
talk.  Contributions that sharpen the PoC thesis, add trace fixtures, improve
determinism guarantees, or fix correctness bugs are welcome.

## Getting started

```bash
git clone https://github.com/sv-pro/agent-world-compiler-poc.git
cd agent-world-compiler-poc
pip install -e ".[dev]"
pytest
```

## Ground rules

1. **Keep it minimal.** The goal is a clear, honest demo – not a framework.
   Prefer a small, correct change over a large, vague one.
2. **No live LLM calls in tests.** All tests must be deterministic and use
   recorded fixture traces.
3. **No cloud dependencies in the main demo path.** The full pipeline must
   run offline with only the files in this repository.
4. **Match the existing code style.** Python 3.12, type-annotated, no third-
   party dependencies beyond `pyyaml` and `pytest`.
5. **Write tests.** Every change to `src/awc/compiler/` or `src/awc/policy/` needs a
   corresponding unit or integration test.

## Adding a new trace

1. Record or craft a JSON fixture in `fixtures/traces/`.
2. Ensure every step has at minimum: `step_id`, `tool`, `action`, `resource`,
   `input_sources`, `tainted`.
3. Derive a profile with `python -m awc.compiler.profiler fixtures/traces/your_trace.json`.
4. If the profile represents a new workflow, compile a manifest with
   `python -m awc.compiler.compile_manifest fixtures/profiles/your_profile.yaml`.

## Submitting changes

Open a pull request against `main`.  CI runs `pytest` automatically.
Please include a short description of what claim the change strengthens.
