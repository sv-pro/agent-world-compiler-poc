"""
test_engine.py – unit tests for the enforcement engine.

Proves the four core invariants:

1. Same manifest + same trace step = same decision (determinism).
2. Undefined actions are denied.
3. Over-scoped tool actions are denied.
4. Tainted data cannot trigger external side effects.
5. Approval-required actions are explicitly surfaced.
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
            "tainted": False,
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
            "tainted": False,
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
            "tainted": False,
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
            "tainted": False,
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
            "tainted": False,
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
            "tainted": False,
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
            "tainted": False,
        }
        decision, _ = evaluate_step(step, minimal_manifest)
        # fork/* is not in permitted_resources (only origin/* is allowed),
        # so this should be DENY not REQUIRE_APPROVAL
        assert decision == Decision.DENY


# ------------------------------------------------------------------ #
# Invariant 4 – Tainted data cannot trigger external side effects     #
# ------------------------------------------------------------------ #


class TestTaintedDataDenied:
    def test_tainted_external_http_denied(self, minimal_manifest: dict) -> None:
        step = {
            "step_id": "step-taint-http",
            "tool": "http_post",
            "action": "network_call",
            "resource": "external://attacker.example.com/collect",
            "input_sources": ["environment"],
            "tainted": True,
        }
        decision, reason = evaluate_step(step, minimal_manifest)
        assert decision == Decision.DENY
        assert "tainted" in reason.lower()

    def test_tainted_external_https_denied(self, minimal_manifest: dict) -> None:
        step = {
            "step_id": "step-taint-https",
            "tool": "http_post",
            "action": "network_call",
            "resource": "https://evil.example.com/exfil",
            "input_sources": ["llm_output"],
            "tainted": True,
        }
        decision, reason = evaluate_step(step, minimal_manifest)
        assert decision == Decision.DENY
        assert "tainted" in reason.lower()

    def test_tainted_non_external_resource_not_auto_denied_by_taint_rule(
        self, minimal_manifest: dict
    ) -> None:
        """
        Tainted data hitting a LOCAL resource is not auto-denied by the taint
        rule (rule 1 only blocks external).  It may still be denied by other
        rules if the action isn't in the allowed set.
        """
        step = {
            "step_id": "step-taint-local",
            "tool": "git_commit",
            "action": "write",
            "resource": "repo://local/commits",
            "input_sources": ["repo_local"],
            "tainted": True,
        }
        decision, reason = evaluate_step(step, minimal_manifest)
        # Rule 1 does NOT fire for local resources.
        # The action IS in the allowed set, so the decision depends on trust.
        # input_sources=["repo_local"] is "trusted" which meets "trusted" req → ALLOW
        assert decision == Decision.ALLOW

    def test_tainted_external_shell_denied(self, minimal_manifest: dict) -> None:
        step = {
            "step_id": "step-taint-shell",
            "tool": "shell_exec",
            "action": "exec",
            "resource": "external://shell.remote.com",
            "input_sources": ["llm_output"],
            "tainted": True,
        }
        decision, reason = evaluate_step(step, minimal_manifest)
        assert decision == Decision.DENY
        assert "tainted" in reason.lower()


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
            "tainted": False,
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
            "tainted": False,
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
            "tainted": False,
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
            "tainted": False,
        }
        decision, _ = evaluate_step(step, minimal_manifest)
        assert decision == Decision.ALLOW
