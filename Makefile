.PHONY: demo test lint install

install:
	pip install -e ".[dev]"

demo:
	python -m demo.run

compile:
	python -m compiler.compile_manifest profiles/repo_safe_write.yaml repo-safe-write "Sergey Vlasov"

evaluate-benign:
	python -m policy.evaluate \
		--trace traces/benign_repo_maintenance.json \
		--manifest manifests/repo-safe-write.yaml

evaluate-unsafe:
	python -m policy.evaluate \
		--trace traces/unsafe_exfiltration.json \
		--manifest manifests/repo-safe-write.yaml; true

test:
	pytest

help:
	@echo "Targets:"
	@echo "  install          Install project and dev dependencies"
	@echo "  demo             Run the end-to-end demo"
	@echo "  compile          Recompile the example manifest from the profile"
	@echo "  evaluate-benign  Evaluate the benign trace against the manifest"
	@echo "  evaluate-unsafe  Evaluate the unsafe trace against the manifest"
	@echo "  test             Run the pytest test suite"
