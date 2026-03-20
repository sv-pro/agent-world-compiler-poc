"""
test_integration.py – end-to-end integration tests.

These tests run the full pipeline (derive profile → compile manifest →
evaluate trace) against the fixture traces and static manifests and assert
on the expected decision sets.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from awc.compiler.profiler import derive_profile
from awc.compiler.compile_manifest import compile_manifest
from awc.policy.engine import Decision, evaluate_step

REPO_ROOT = Path(__file__).resolve().parent.parent
BENIGN_TRACE_PATH = REPO_ROOT / "fixtures" / "traces" / "benign_repo_maintenance.json"
UNSAFE_TRACE_PATH = REPO_ROOT / "fixtures" / "traces" / "unsafe_exfiltration.json"
STATIC_MANIFEST_PATH = REPO_ROOT / "fixtures" / "manifests" / "repo-safe-write.yaml"


def _load_trace(path: Path) -> dict:
    with path.open() as fh:
        return json.load(fh)


def _load_manifest(path: Path) -> dict:
    with path.open() as fh:
        return yaml.safe_load(fh)


class TestBenignTraceAgainstStaticManifest:
    """
    The benign maintenance trace should never produce a DENY when evaluated
    against the repo-safe-write manifest.
    """

    def test_no_deny_in_benign_trace(self, static_manifest: dict) -> None:
        trace = _load_trace(BENIGN_TRACE_PATH)
        for step in trace["steps"]:
            decision, reason = evaluate_step(step, static_manifest)
            assert decision != Decision.DENY, (
                f"Step {step['step_id']} ({step['tool']}) unexpectedly DENIED: {reason}"
            )

    def test_git_push_step_requires_approval(self, static_manifest: dict) -> None:
        trace = _load_trace(BENIGN_TRACE_PATH)
        push_steps = [s for s in trace["steps"] if s["tool"] == "git_push"]
        assert push_steps, "No git_push step found in benign trace."
        for step in push_steps:
            decision, _ = evaluate_step(step, static_manifest)
            assert decision == Decision.REQUIRE_APPROVAL


class TestUnsafeTraceAgainstStaticManifest:
    """
    The unsafe exfiltration trace should produce at least one DENY for every
    step that touches an external or tainted resource.
    """

    def test_all_unsafe_steps_denied(self, static_manifest: dict) -> None:
        trace = _load_trace(UNSAFE_TRACE_PATH)
        for step in trace["steps"]:
            decision, reason = evaluate_step(step, static_manifest)
            assert decision == Decision.DENY, (
                f"Step {step['step_id']} ({step['tool']}) was NOT denied: {decision} — {reason}"
            )


class TestFullPipeline:
    """
    Derive profile from benign trace, compile a manifest, evaluate both traces
    against the compiled manifest and assert the same decisions as with the
    static manifest.
    """

    @pytest.fixture()
    def compiled_manifest(self) -> dict:
        profile = derive_profile([BENIGN_TRACE_PATH], profile_id="repo_safe_write")
        return compile_manifest(profile, manifest_id="repo-safe-write-test", author="test-suite")

    def test_benign_trace_no_deny_compiled_manifest(self, compiled_manifest: dict) -> None:
        trace = _load_trace(BENIGN_TRACE_PATH)
        for step in trace["steps"]:
            decision, reason = evaluate_step(step, compiled_manifest)
            assert decision != Decision.DENY, (
                f"Step {step['step_id']} unexpectedly DENIED: {reason}"
            )

    def test_unsafe_trace_all_denied_compiled_manifest(self, compiled_manifest: dict) -> None:
        trace = _load_trace(UNSAFE_TRACE_PATH)
        for step in trace["steps"]:
            decision, reason = evaluate_step(step, compiled_manifest)
            assert decision == Decision.DENY, (
                f"Step {step['step_id']} was NOT denied: {decision} — {reason}"
            )

    def test_same_manifest_same_step_same_decision_is_deterministic(
        self, compiled_manifest: dict
    ) -> None:
        trace = _load_trace(BENIGN_TRACE_PATH)
        step = trace["steps"][0]
        results = [evaluate_step(step, compiled_manifest)[0] for _ in range(5)]
        assert len(set(results)) == 1, "Decisions are not deterministic."
