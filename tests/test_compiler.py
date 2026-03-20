"""
test_compiler.py – tests for profile derivation and manifest compilation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # type: ignore[import-untyped]

from awc.compiler.profiler import derive_profile, CapabilityProfile
from awc.compiler.compile_manifest import compile_manifest


REPO_ROOT = Path(__file__).resolve().parent.parent
BENIGN_TRACE = REPO_ROOT / "fixtures" / "traces" / "benign_repo_maintenance.json"
UNSAFE_TRACE = REPO_ROOT / "fixtures" / "traces" / "unsafe_exfiltration.json"


class TestProfiler:
    def test_profile_derived_from_benign_trace(self) -> None:
        profile = derive_profile([BENIGN_TRACE], profile_id="test_benign")
        assert profile.profile_id == "test_benign"
        assert "git_commit" in profile.allowed_tools
        assert "git_push" in profile.allowed_tools
        assert "fs_read" in profile.allowed_tools

    def test_tainted_steps_excluded_from_profile(self) -> None:
        profile = derive_profile([UNSAFE_TRACE], profile_id="test_unsafe")
        # All steps in the unsafe trace are tainted → no tools allowed
        assert len(profile.allowed_tools) == 0
        assert profile.tainted_steps_observed > 0

    def test_tainted_step_count_correct(self) -> None:
        profile = derive_profile([UNSAFE_TRACE], profile_id="test_unsafe_count")
        assert profile.tainted_steps_observed == 4  # all 4 steps are tainted

    def test_multi_trace_profile_merges_tools(self) -> None:
        profile = derive_profile([BENIGN_TRACE, UNSAFE_TRACE], profile_id="test_multi")
        # Unsafe trace contributes 0 tools (all tainted); benign contributes its set
        assert "git_commit" in profile.allowed_tools
        assert profile.tainted_steps_observed == 4

    def test_profile_to_dict_is_serialisable(self) -> None:
        profile = derive_profile([BENIGN_TRACE], profile_id="test_serial")
        d = profile.to_dict()
        out = yaml.dump(d)
        assert "test_serial" in out


class TestCompileManifest:
    def test_compile_produces_manifest_with_required_keys(self) -> None:
        profile = derive_profile([BENIGN_TRACE], profile_id="repo_safe_write")
        manifest = compile_manifest(profile)
        assert "manifest_id" in manifest
        assert "allowed_actions" in manifest
        assert "denied_actions" in manifest
        assert "approval_required" in manifest
        assert "capability_constraints" in manifest
        assert "input_trust" in manifest
        assert "provenance" in manifest

    def test_remote_resources_generate_approval_required(self) -> None:
        profile = derive_profile([BENIGN_TRACE], profile_id="repo_safe_write")
        manifest = compile_manifest(profile)
        approval_actions = [a["action"] for a in manifest["approval_required"]]
        # git_push is the tool that accesses repo://remote/origin/*
        assert "git_push" in approval_actions

    def test_always_denied_actions_present(self) -> None:
        profile = derive_profile([BENIGN_TRACE], profile_id="repo_safe_write")
        manifest = compile_manifest(profile)
        denied_actions = [d["action"] for d in manifest["denied_actions"]]
        assert "http_post" in denied_actions
        assert "env_read" in denied_actions

    def test_manifest_id_override(self) -> None:
        profile = derive_profile([BENIGN_TRACE], profile_id="repo_safe_write")
        manifest = compile_manifest(profile, manifest_id="custom-id")
        assert manifest["manifest_id"] == "custom-id"

    def test_undefined_actions_constraint_is_deny(self) -> None:
        profile = derive_profile([BENIGN_TRACE], profile_id="repo_safe_write")
        manifest = compile_manifest(profile)
        assert manifest["capability_constraints"]["undefined_actions"] == "deny"
