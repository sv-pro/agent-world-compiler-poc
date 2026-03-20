.PHONY: demo test lint install help

install:
	pip install -e ".[dev]"

demo:
	python -m examples.demo_pipeline

compile:
	python -m awc.compiler.compile_manifest fixtures/profiles/repo_safe_write.yaml repo-safe-write "Sergey Vlasov"

evaluate-benign:
	python -m awc.policy.evaluate \
		--trace fixtures/traces/benign_repo_maintenance.json \
		--manifest fixtures/manifests/repo-safe-write.yaml

evaluate-unsafe:
	python -m awc.policy.evaluate \
		--trace fixtures/traces/unsafe_exfiltration.json \
		--manifest fixtures/manifests/repo-safe-write.yaml; true

test:
	pytest

help:
	@echo "Targets:"
	@echo "  install          Install project and dev dependencies"
	@echo "  demo             Run the end-to-end demo pipeline"
	@echo "  compile          Recompile the example manifest from the profile"
	@echo "  evaluate-benign  Evaluate the benign trace against the manifest"
	@echo "  evaluate-unsafe  Evaluate the unsafe trace against the manifest"
	@echo "  test             Run the pytest test suite"
