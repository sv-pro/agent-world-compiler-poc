"""
test_engine.py – unit tests for the enforcement engine.

Proves the core invariants:

1. Same manifest + same trace step = same decision (determinism).
2. Undefined actions are denied.
3. Over-scoped tool actions are denied.
4. Tainted data cannot trigger external side effects.
   Taint is DERIVED from input_sources, not from the raw 'tainted' field.
5. Approval-required actions are explicitly surfaced.
6. Legacy 'tainted' annotation is ignored; provenance is the source of truth.
"""

from __future__ import annotations

import pytest

from awc.policy.engine import Decision, evaluate_step


# ------------------------------------------------------------------ #
# Invariant 1 – Determinism: same inputs → same output               #
# ------------------------------------------------------------------ #


class TestDeterminism:
    def test_repeated_calls_return_same_decision(self, minimal_manifest: dict) -> None:
        step = {
            "step_id": "step-001",
            "tool": "git_commit",
            "action": "write",
            "resource": "repo://local/commits",
            "input_sources": ["repo_local"],
        }
        d1, r1 = evaluate_step(step, minimal_manifest)
        d2, r2 = evaluate_step(step, minimal_manifest)
        assert d1 == d2
        assert r1 == r2

    def test_determinism_across_multiple_calls(self, minimal_manifest: dict) -> None:
        step = {
            "step_id": "step-X",
            "tool": "git_push",
            "action": "write",
            "resource": "repo://remote/origin/main",
            "input_sources": ["repo_local"],
        }
        decisions = {evaluate_step(step, minimal_manifest)[0] for _ in range(10)}
        assert len(decisions) == 1  # all calls return the same decision


# ------------------------------------------------------------------ #
# Invariant 2 – Undefined actions are denied                          #
# ------------------------------------------------------------------ #


class TestUndefinedActionsDenied:
    def test_unknown_action_is_denied(self, minimal_manifest: dict) -> None:
        step = {
            "step_id": "step-unk",
            "tool": "rm_rf",
            "action": "delete",
            "resource": "repo://local/src",
            "input_sources": ["repo_local"],
        }
        decision, reason = evaluate_step(step, minimal_manifest)
        assert decision == Decision.DENY
        assert "not in the allowed set" in reason.lower() or "denied" in reason.lower()

    def test_known_action_wrong_resource_is_denied(self, minimal_manifest: dict) -> None:
        step = {
            "step_id": "step-wr",
            "tool": "git_commit",
            "action": "write",
            "resource": "external://somewhere.com/data",
            "input_sources": ["repo_local"],
        }
        decision, _ = evaluate_step(step, minimal_manifest)
        assert decision == Decision.DENY


# ------------------------------------------------------------------ #
# Invariant 3 – Over-scoped tool actions are denied                   #
# ------------------------------------------------------------------ #


class TestOverScopedDenied:
    def test_http_post_denied(self, minimal_manifest: dict) -> None:
        step = {
            "step_id": "step-http",
            "tool": "http_post",
            "action": "network_call",
            "resource": "external://api.example.com/data",
            "input_sources": ["repo_local"],
        }
        decision, reason = evaluate_step(step, minimal_manifest)
        assert decision == Decision.DENY
        assert "http_post" in reason.lower() or "denied" in reason.lower()

    def test_env_read_denied(self, minimal_manifest: dict) -> None:
        step = {
            "step_id": "step-env",
            "tool": "env_read",
            "action": "read",
            "resource": "env://SECRET_TOKEN",
            "input_sources": ["environment"],
        }
        decision, _ = evaluate_step(step, minimal_manifest)
        assert decision == Decision.DENY

    def test_push_to_unauthorized_remote_denied(self, minimal_manifest: dict) -> None:
        step = {
            "step_id": "step-fork",
            "tool": "git_push",
            "action": "write",
            "resource": "repo://remote/fork/main",  # only origin/* is in allowed set
            "input_sources": ["repo_local"],
        }
        decision, _ = evaluate_step(step, minimal_manifest)
        # fork/* is not in permitted_resources (only origin/* is allowed),
        # so this should be DENY not REQUIRE_APPROVAL
        assert decision == Decision.DENY


# ------------------------------------------------------------------ #
# Invariant 4 – Tainted data cannot trigger external side effects     #
#                                                                     #
# Taint is DERIVED from input_sources, not from 'tainted' field.      #
# ------------------------------------------------------------------ #


class TestTaintedDataDenied:
    def test_taint_derived_from_untrusted_source_blocks_external(
        self, minimal_manifest: dict
    ) -> None:
        """Taint derived from input_sources → external resource → DENY."""
        step = {
            "step_id": "step-taint-http",
            "tool": "http_post",
            "action": "network_call",
            "resource": "external://attacker.example.com/collect",
            "input_sources": ["environment"],  # environment → untrusted → tainted
            # No 'tainted' field at all – taint is derived from provenance.
        }
        decision, reason = evaluate_step(step, minimal_manifest)
        assert decision == Decision.DENY
        assert "tainted" in reason.lower()

    def test_legacy_tainted_false_does_not_override_derived_taint(
        self, minimal_manifest: dict
    ) -> None:
        """
        Even if a step carries 'tainted: false' as a legacy annotation, if
        provenance says tainted (untrusted source → external resource) → DENY.
        """
        step = {
            "step_id": "step-legacy",
            "tool": "http_post",
            "action": "network_call",
            "resource": "https://evil.example.com/exfil",
            "input_sources": ["llm_output"],  # untrusted → derived tainted
            "tainted": False,  # legacy annotation, must be ignored
        }
        decision, reason = evaluate_step(step, minimal_manifest)
        assert decision == Decision.DENY, (
            "Derived taint from 'llm_output' should override the legacy tainted=False annotation"
        )
        assert "tainted" in reason.lower()

    def test_tainted_https_external_denied(self, minimal_manifest: dict) -> None:
        step = {
            "step_id": "step-taint-https",
            "tool": "http_post",
            "action": "network_call",
            "resource": "https://evil.example.com/exfil",
            "input_sources": ["llm_output"],  # untrusted → tainted
        }
        decision, reason = evaluate_step(step, minimal_manifest)
        assert decision == Decision.DENY
        assert "tainted" in reason.lower()

    def test_tainted_local_resource_not_auto_denied_by_taint_rule(
        self, minimal_manifest: dict
    ) -> None:
        """
        Rule 1 only blocks tainted data reaching EXTERNAL resources.
        A tainted step targeting a local resource falls through to other rules.
        Here environment (untrusted) → tainted, but resource is local.
        The step is denied by the trust check (trust_required=trusted,
        environment=untrusted), NOT by the taint-external rule.
        """
        step = {
            "step_id": "step-taint-local",
            "tool": "git_commit",
            "action": "write",
            "resource": "repo://local/commits",
            "input_sources": ["environment"],  # untrusted → derived tainted
        }
        decision, reason = evaluate_step(step, minimal_manifest)
        # Rule 1 (taint+external) does NOT fire – resource is local.
        assert "external" not in reason.lower() or "tainted data cannot trigger external" not in reason.lower()
        # Denied instead by trust check.
        assert decision == Decision.DENY
        assert "trust" in reason.lower()

    def test_tainted_external_shell_denied(self, minimal_manifest: dict) -> None:
        step = {
            "step_id": "step-taint-shell",
            "tool": "shell_exec",
            "action": "exec",
            "resource": "external://shell.remote.com",
            "input_sources": ["llm_output"],  # untrusted → tainted
        }
        decision, reason = evaluate_step(step, minimal_manifest)
        assert decision == Decision.DENY
        assert "tainted" in reason.lower()

    def test_pre_computed_derived_taint_is_respected(self, minimal_manifest: dict) -> None:
        """
        When derived_taint=True is passed explicitly (e.g. from propagation),
        the engine uses it even if input_sources are trusted.
        This covers the propagation path: step depends on a tainted step.
        """
        step = {
            "step_id": "step-propagated",
            "tool": "http_post",
            "action": "network_call",
            "resource": "external://attacker.example.com/collect",
            "input_sources": ["repo_local"],  # trusted by source, but tainted by propagation
        }
        decision, reason = evaluate_step(
            step, minimal_manifest,
            derived_taint=True,
            taint_reasons=["depends_on_tainted:step-001"],
        )
        assert decision == Decision.DENY
        assert "tainted" in reason.lower()
        assert "step-001" in reason


# ------------------------------------------------------------------ #
# Invariant 5 – Approval-required actions are explicitly surfaced     #
# ------------------------------------------------------------------ #


class TestApprovalRequired:
    def test_git_push_to_origin_requires_approval(self, minimal_manifest: dict) -> None:
        step = {
            "step_id": "step-push",
            "tool": "git_push",
            "action": "write",
            "resource": "repo://remote/origin/main",
            "input_sources": ["repo_local"],
        }
        decision, reason = evaluate_step(step, minimal_manifest)
        assert decision == Decision.REQUIRE_APPROVAL
        assert "approval" in reason.lower()

    def test_approval_reason_is_non_empty(self, minimal_manifest: dict) -> None:
        step = {
            "step_id": "step-push2",
            "tool": "git_push",
            "action": "write",
            "resource": "repo://remote/origin/feature",
            "input_sources": ["repo_local"],
        }
        _, reason = evaluate_step(step, minimal_manifest)
        assert reason.strip() != ""


# ------------------------------------------------------------------ #
# Trust-level enforcement                                             #
# ------------------------------------------------------------------ #


class TestTrustLevel:
    def test_untrusted_source_denied_for_trusted_required(self, minimal_manifest: dict) -> None:
        step = {
            "step_id": "step-untrusted",
            "tool": "git_commit",
            "action": "write",
            "resource": "repo://local/commits",
            "input_sources": ["llm_output"],  # llm_output → untrusted
        }
        decision, reason = evaluate_step(step, minimal_manifest)
        assert decision == Decision.DENY
        assert "trust" in reason.lower()

    def test_trusted_source_allowed(self, minimal_manifest: dict) -> None:
        step = {
            "step_id": "step-trusted",
            "tool": "git_commit",
            "action": "write",
            "resource": "repo://local/commits",
            "input_sources": ["repo_local"],
        }
        decision, _ = evaluate_step(step, minimal_manifest)
        assert decision == Decision.ALLOW
