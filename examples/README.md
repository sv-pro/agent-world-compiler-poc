# Examples

Runnable scripts demonstrating the Agent World Compiler pipeline.

| Script | What it shows |
| --- | --- |
| `record_and_compile.py` | **Full pipeline from scratch** — records a workflow with `TraceRecorder`, then profiles, compiles, and enforces without touching any fixture file |
| `demo_pipeline.py` | Full pipeline from fixture traces (Observe → Profile → Manifest → Enforce) with both benign and unsafe traces |
| `derive_and_compile.py` | Compiler pipeline only: derive a profile from a fixture, then compile it into a manifest |
| `evaluate_example.py` | Programmatic use of the enforcement engine against individual steps |

## Running

```bash
# Full demo
python -m examples.demo_pipeline

# Or via Makefile
make demo
```
