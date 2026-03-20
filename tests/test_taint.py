"""
test_taint.py – unit tests for the deterministic taint derivation module.

Proves that taint is a function of provenance and flow, not a manually
assigned label.
"""

from __future__ import annotations

import pytest

from awc.policy.taint import DEFAULT_INPUT_TRUST, compute_trace_taint, derive_source_taint


TRUST_MAP = {
    "repo_local": "trusted",
    "environment": "untrusted",
    "llm_output": "untrusted",
    "tool_output": "conditional",
}


# ------------------------------------------------------------------ #
# derive_source_taint – single step, no propagation                  #
# ------------------------------------------------------------------ #


class TestDeriveSourceTaint:
    def test_trusted_source_not_tainted(self) -> None:
        tainted, reasons = derive_source_taint(["repo_local"], TRUST_MAP)
        assert tainted is False
        assert reasons == []

    def test_untrusted_source_is_tainted(self) -> None:
        tainted, reasons = derive_source_taint(["environment"], TRUST_MAP)
        assert tainted is True
        assert any("environment" in r for r in reasons)

    def test_llm_output_is_tainted(self) -> None:
        tainted, reasons = derive_source_taint(["llm_output"], TRUST_MAP)
        assert tainted is True
        assert any("llm_output" in r for r in reasons)

    def test_conditional_source_is_tainted(self) -> None:
        # 'conditional' is treated as tainted in this PoC
        tainted, reasons = derive_source_taint(["tool_output"], TRUST_MAP)
        assert tainted is True

    def test_unknown_source_defaults_to_untrusted(self) -> None:
        tainted, reasons = derive_source_taint(["mystery_source"], TRUST_MAP)
        assert tainted is True
        assert any("mystery_source" in r for r in reasons)

    def test_mixed_sources_any_untrusted_taints(self) -> None:
        # repo_local is trusted, but environment is untrusted → tainted
        tainted, reasons = derive_source_taint(["repo_local", "environment"], TRUST_MAP)
        assert tainted is True

    def test_empty_sources_not_tainted(self) -> None:
        tainted, reasons = derive_source_taint([], TRUST_MAP)
        assert tainted is False
        assert reasons == []

    def test_reason_format(self) -> None:
        _, reasons = derive_source_taint(["environment"], TRUST_MAP)
        assert "untrusted_input:environment" in reasons


# ------------------------------------------------------------------ #
# compute_trace_taint – taint propagation through depends_on         #
# ------------------------------------------------------------------ #


class TestComputeTraceTaint:
    def test_single_trusted_step_not_tainted(self) -> None:
        steps = [
            {
                "step_id": "step-001",
                "input_sources": ["repo_local"],
                "depends_on": [],
            }
        ]
        state = compute_trace_taint(steps, TRUST_MAP)
        tainted, reasons = state["step-001"]
        assert tainted is False
        assert reasons == []

    def test_single_untrusted_step_tainted(self) -> None:
        steps = [
            {
                "step_id": "step-001",
                "input_sources": ["environment"],
                "depends_on": [],
            }
        ]
        state = compute_trace_taint(steps, TRUST_MAP)
        tainted, reasons = state["step-001"]
        assert tainted is True
        assert "untrusted_input:environment" in reasons

    def test_taint_propagates_through_depends_on(self) -> None:
        """Step B depends on tainted step A → step B is also tainted."""
        steps = [
            {
                "step_id": "step-001",
                "input_sources": ["environment"],  # untrusted → tainted
                "depends_on": [],
            },
            {
                "step_id": "step-002",
                "input_sources": ["repo_local"],  # trusted on its own
                "depends_on": ["step-001"],         # but depends on tainted step
            },
        ]
        state = compute_trace_taint(steps, TRUST_MAP)

        tainted_a, _ = state["step-001"]
        tainted_b, reasons_b = state["step-002"]

        assert tainted_a is True
        assert tainted_b is True, "Taint must propagate from step-001 to step-002"
        assert "depends_on_tainted:step-001" in reasons_b

    def test_taint_does_not_propagate_from_clean_step(self) -> None:
        """A dependency on a non-tainted step does not introduce taint."""
        steps = [
            {
                "step_id": "step-001",
                "input_sources": ["repo_local"],  # trusted → not tainted
                "depends_on": [],
            },
            {
                "step_id": "step-002",
                "input_sources": ["repo_local"],
                "depends_on": ["step-001"],
            },
        ]
        state = compute_trace_taint(steps, TRUST_MAP)
        tainted_b, reasons_b = state["step-002"]
        assert tainted_b is False
        assert reasons_b == []

    def test_transitive_propagation(self) -> None:
        """Taint propagates across multiple hops: A (tainted) → B → C."""
        steps = [
            {"step_id": "step-001", "input_sources": ["environment"], "depends_on": []},
            {"step_id": "step-002", "input_sources": ["repo_local"], "depends_on": ["step-001"]},
            {"step_id": "step-003", "input_sources": ["repo_local"], "depends_on": ["step-002"]},
        ]
        state = compute_trace_taint(steps, TRUST_MAP)
        assert state["step-001"][0] is True
        assert state["step-002"][0] is True
        assert state["step-003"][0] is True, "Taint should propagate transitively"

    def test_unknown_dependency_raises_valueerror(self) -> None:
        steps = [
            {
                "step_id": "step-002",
                "input_sources": ["repo_local"],
                "depends_on": ["step-does-not-exist"],
            }
        ]
        with pytest.raises(ValueError, match="depends_on unknown step"):
            compute_trace_taint(steps, TRUST_MAP)

    def test_all_steps_present_in_result(self) -> None:
        steps = [
            {"step_id": "step-001", "input_sources": ["repo_local"], "depends_on": []},
            {"step_id": "step-002", "input_sources": ["repo_local"], "depends_on": ["step-001"]},
        ]
        state = compute_trace_taint(steps, TRUST_MAP)
        assert "step-001" in state
        assert "step-002" in state

    def test_reason_includes_both_source_and_dependency(self) -> None:
        """A step tainted both by its own source AND by a dependency has both reasons."""
        steps = [
            {"step_id": "step-001", "input_sources": ["environment"], "depends_on": []},
            {"step_id": "step-002", "input_sources": ["llm_output"], "depends_on": ["step-001"]},
        ]
        state = compute_trace_taint(steps, TRUST_MAP)
        _, reasons = state["step-002"]
        assert "untrusted_input:llm_output" in reasons
        assert "depends_on_tainted:step-001" in reasons


# ------------------------------------------------------------------ #
# Determinism guarantee                                               #
# ------------------------------------------------------------------ #


class TestTaintDeterminism:
    def test_same_inputs_same_result(self) -> None:
        steps = [
            {"step_id": "step-001", "input_sources": ["environment"], "depends_on": []},
            {"step_id": "step-002", "input_sources": ["repo_local"], "depends_on": ["step-001"]},
        ]
        results = [compute_trace_taint(steps, TRUST_MAP) for _ in range(5)]
        for state in results[1:]:
            assert state["step-001"] == results[0]["step-001"]
            assert state["step-002"] == results[0]["step-002"]

    def test_default_trust_map_is_consistent(self) -> None:
        assert DEFAULT_INPUT_TRUST["repo_local"] == "trusted"
        assert DEFAULT_INPUT_TRUST["environment"] == "untrusted"
        assert DEFAULT_INPUT_TRUST["llm_output"] == "untrusted"
