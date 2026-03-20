# Examples

Runnable scripts demonstrating the Agent World Compiler pipeline.

| Script | What it shows |
|---|---|
| `demo_pipeline.py` | Full four-stage pipeline (Observe → Profile → Manifest → Enforce) with both benign and unsafe traces |
| `derive_and_compile.py` | Compiler pipeline only: derive a profile, then compile it into a manifest |
| `evaluate_example.py` | Programmatic use of the enforcement engine against individual steps |

## Running

```bash
# Full demo
python -m examples.demo_pipeline

# Or via Makefile
make demo
```
