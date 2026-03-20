"""
conftest.py – shared pytest fixtures for the Agent World Compiler PoC.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture()
def static_manifest(repo_root: Path) -> dict:
    """Load the static repo-safe-write manifest from disk."""
    path = repo_root / "manifests" / "repo-safe-write.yaml"
    with path.open() as fh:
        return yaml.safe_load(fh)


@pytest.fixture()
def minimal_manifest() -> dict:
    """A minimal manifest used for isolated engine tests."""
    return {
        "manifest_id": "test-manifest",
        "version": "1.0",
        "input_trust": {
            "repo_local": "trusted",
            "environment": "untrusted",
            "llm_output": "untrusted",
            "tool_output": "conditional",
        },
        "allowed_actions": [
            {
                "action": "git_commit",
                "permitted_resources": ["repo://local/*"],
                "trust_required": "trusted",
                "taint_ok": False,
            },
            {
                "action": "git_push",
                "permitted_resources": ["repo://remote/origin/*"],
                "trust_required": "trusted",
                "taint_ok": False,
            },
        ],
        "approval_required": [
            {
                "action": "git_push",
                "resource_pattern": "repo://remote/*",
                "reason": "All remote pushes require explicit operator approval.",
            }
        ],
        "denied_actions": [
            {"action": "http_post", "reason": "Outbound HTTP calls are not part of the declared workflow."},
            {"action": "env_read", "reason": "Environment variable access is not part of the declared workflow."},
        ],
        "capability_constraints": {
            "taint_propagation": "deny_external",
            "max_scope": "single_repo",
            "allow_network_calls": False,
            "allow_env_secrets": False,
            "undefined_actions": "deny",
        },
    }
