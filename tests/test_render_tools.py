"""
tests/test_render_tools.py – focused tests for the render_tools layer.

Tests verify five properties:
1. Manifest capability → rendered tool  (basic projection)
2. Rendered tools preserve narrowing constraints from the manifest
3. Denied / absent capabilities are never rendered as tools
4. Tool naming is deterministic
5. No expansion beyond manifest allowed_actions (no-expansion invariant)
"""

from __future__ import annotations

import pytest

from awc.compiler.render_tools import render_tools, RenderedTool


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _manifest(allowed: list[dict], denied: list[dict] | None = None) -> dict:
    """Build a minimal manifest dict for testing."""
    return {
        "manifest_id": "test",
        "version": "1.0",
        "input_trust": {"repo_local": "trusted", "environment": "untrusted"},
        "allowed_actions": allowed,
        "denied_actions": denied or [],
        "approval_required": [],
        "capability_constraints": {"undefined_actions": "deny"},
    }


def _entry(
    action: str,
    resources: list[str],
    trust_required: str = "trusted",
    taint_ok: bool = False,
) -> dict:
    """Build a single allowed_action manifest entry."""
    return {
        "action": action,
        "permitted_resources": resources,
        "trust_required": trust_required,
        "taint_ok": taint_ok,
    }


# ---------------------------------------------------------------------------
# 1. Manifest capability → rendered tool
# ---------------------------------------------------------------------------

class TestCapabilityToRenderedTool:
    def test_one_tool_per_allowed_action(self):
        m = _manifest([
            _entry("git_push", ["repo://remote/origin/*"]),
            _entry("fs_read", ["repo://local/*"]),
        ])
        assert len(render_tools(m)) == 2

    def test_returns_rendered_tool_instances(self):
        m = _manifest([_entry("git_push", ["repo://remote/origin/*"])])
        tools = render_tools(m)
        assert all(isinstance(t, RenderedTool) for t in tools)

    def test_base_tool_matches_manifest_action(self):
        m = _manifest([_entry("git_push", ["repo://remote/origin/*"])])
        tool = render_tools(m)[0]
        assert tool.base_tool == "git_push"

    def test_action_matches_manifest_action(self):
        m = _manifest([_entry("fs_read", ["repo://local/*"])])
        tool = render_tools(m)[0]
        assert tool.action == "fs_read"

    def test_empty_allowed_actions_yields_no_tools(self):
        assert render_tools(_manifest([])) == []

    def test_order_preserved(self):
        actions = ["git_push", "fs_read", "git_commit", "shell_exec"]
        m = _manifest([_entry(a, ["repo://local/*"]) for a in actions])
        rendered_actions = [t.base_tool for t in render_tools(m)]
        assert rendered_actions == actions

    def test_tool_has_description(self):
        m = _manifest([_entry("git_push", ["repo://remote/origin/*"])])
        tool = render_tools(m)[0]
        assert tool.description
        assert "git_push" in tool.description

    def test_tool_has_input_schema(self):
        m = _manifest([_entry("git_push", ["repo://remote/origin/*"])])
        tool = render_tools(m)[0]
        assert isinstance(tool.input_schema, dict)
        assert "properties" in tool.input_schema

    def test_to_dict_serialisation(self):
        m = _manifest([_entry("git_push", ["repo://remote/origin/*"])])
        tool = render_tools(m)[0]
        d = tool.to_dict()
        for key in ("name", "base_tool", "action", "description",
                    "input_schema", "fixed_args", "allowed_resource_patterns",
                    "trust_required", "taint_ok"):
            assert key in d


# ---------------------------------------------------------------------------
# 2. Rendered tools preserve narrowing constraints
# ---------------------------------------------------------------------------

class TestNarrowingConstraints:
    def test_resource_patterns_preserved(self):
        m = _manifest([_entry("git_push", ["repo://remote/origin/*"])])
        tool = render_tools(m)[0]
        assert tool.allowed_resource_patterns == ["repo://remote/origin/*"]

    def test_trust_required_preserved(self):
        m = _manifest([_entry("fs_read", ["repo://local/*"], trust_required="trusted")])
        assert render_tools(m)[0].trust_required == "trusted"

    def test_taint_ok_false_preserved(self):
        m = _manifest([_entry("fs_read", ["repo://local/*"], taint_ok=False)])
        assert render_tools(m)[0].taint_ok is False

    def test_taint_ok_true_preserved(self):
        m = _manifest([_entry("shell_exec", ["shell://local"], taint_ok=True)])
        assert render_tools(m)[0].taint_ok is True

    def test_fixed_args_extracted_for_origin(self):
        m = _manifest([_entry("git_push", ["repo://remote/origin/*"])])
        assert render_tools(m)[0].fixed_args == {"remote": "origin"}

    def test_fixed_args_extracted_for_named_remote(self):
        m = _manifest([_entry("git_push", ["repo://remote/upstream/*"])])
        assert render_tools(m)[0].fixed_args == {"remote": "upstream"}

    def test_fixed_args_empty_for_local(self):
        m = _manifest([_entry("fs_read", ["repo://local/*"])])
        assert render_tools(m)[0].fixed_args == {}

    def test_fixed_args_empty_for_shell(self):
        m = _manifest([_entry("shell_exec", ["shell://local"])])
        assert render_tools(m)[0].fixed_args == {}

    def test_description_contains_resource_pattern(self):
        m = _manifest([_entry("git_push", ["repo://remote/origin/*"])])
        tool = render_tools(m)[0]
        assert "repo://remote/origin/*" in tool.description


# ---------------------------------------------------------------------------
# 3. Denied / absent capabilities not exposed as tools
# ---------------------------------------------------------------------------

class TestNoExposureOfDenied:
    def test_denied_actions_not_rendered(self):
        m = _manifest(
            allowed=[_entry("git_commit", ["repo://local/*"])],
            denied=[
                {"action": "http_post", "reason": "outbound not allowed"},
                {"action": "env_read", "reason": "secret access denied"},
            ],
        )
        tool_names = {t.base_tool for t in render_tools(m)}
        assert "http_post" not in tool_names
        assert "env_read" not in tool_names

    def test_only_allowed_tools_rendered(self):
        m = _manifest(
            allowed=[_entry("git_commit", ["repo://local/*"])],
            denied=[{"action": "http_post", "reason": "not allowed"}],
        )
        tools = render_tools(m)
        assert len(tools) == 1
        assert tools[0].base_tool == "git_commit"

    def test_empty_allowed_with_denied_yields_no_tools(self):
        m = _manifest(
            allowed=[],
            denied=[
                {"action": "http_post", "reason": "not allowed"},
                {"action": "env_read", "reason": "not allowed"},
            ],
        )
        assert render_tools(m) == []

    def test_approval_required_does_not_expand_tools(self):
        # approval_required entries should not produce additional rendered tools
        m = _manifest(allowed=[_entry("git_push", ["repo://remote/origin/*"])])
        m["approval_required"] = [
            {"action": "git_push", "resource_pattern": "repo://remote/*",
             "reason": "needs approval"},
        ]
        tools = render_tools(m)
        # Still only one tool; approval_required is not a source of new tools
        assert len(tools) == 1


# ---------------------------------------------------------------------------
# 4. Naming is deterministic
# ---------------------------------------------------------------------------

class TestDeterministicNaming:
    def test_git_push_origin_name(self):
        m = _manifest([_entry("git_push", ["repo://remote/origin/*"])])
        assert render_tools(m)[0].name == "git_push_origin_only"

    def test_fs_read_local_name(self):
        m = _manifest([_entry("fs_read", ["repo://local/*"])])
        assert render_tools(m)[0].name == "fs_read_repo_only"

    def test_shell_exec_local_name(self):
        m = _manifest([_entry("shell_exec", ["shell://local"])])
        assert render_tools(m)[0].name == "shell_exec_local_only"

    def test_git_commit_local_name(self):
        m = _manifest([_entry("git_commit", ["repo://local/*"])])
        assert render_tools(m)[0].name == "git_commit_repo_only"

    def test_same_manifest_same_names(self):
        m = _manifest([
            _entry("git_push", ["repo://remote/origin/*"]),
            _entry("fs_read", ["repo://local/*"]),
        ])
        assert [t.name for t in render_tools(m)] == [t.name for t in render_tools(m)]

    def test_names_unique_for_different_actions_same_resource(self):
        m = _manifest([
            _entry("fs_read", ["repo://local/*"]),
            _entry("git_commit", ["repo://local/*"]),
        ])
        names = [t.name for t in render_tools(m)]
        assert len(names) == len(set(names))

    def test_name_is_valid_identifier_like(self):
        m = _manifest([_entry("git_push", ["repo://remote/origin/*"])])
        name = render_tools(m)[0].name
        # name should be lowercase alphanumeric + underscores only
        import re
        assert re.match(r"^[a-z0-9_]+$", name), f"Name not identifier-safe: {name!r}"


# ---------------------------------------------------------------------------
# 5. No expansion beyond manifest (no-expansion invariant)
# ---------------------------------------------------------------------------

class TestNoExpansionInvariant:
    def test_tool_count_equals_allowed_count(self):
        entries = [
            _entry("git_push", ["repo://remote/origin/*"]),
            _entry("fs_read", ["repo://local/*"]),
            _entry("git_commit", ["repo://local/*"]),
        ]
        m = _manifest(entries)
        assert len(render_tools(m)) == len(entries)

    def test_no_new_resource_patterns_introduced(self):
        """Each rendered tool's resource patterns must be a subset of the manifest entry's."""
        m = _manifest([_entry("fs_read", ["repo://local/*"])])
        tool = render_tools(m)[0]
        manifest_patterns = set(m["allowed_actions"][0]["permitted_resources"])
        rendered_patterns = set(tool.allowed_resource_patterns)
        assert rendered_patterns <= manifest_patterns

    def test_base_tools_subset_of_manifest_actions(self):
        """render_tools never fabricates tools not in allowed_actions."""
        m = _manifest([_entry("git_push", ["repo://remote/origin/*"])])
        base_tools = {t.base_tool for t in render_tools(m)}
        allowed_actions = {e["action"] for e in m["allowed_actions"]}
        assert base_tools <= allowed_actions

    def test_trust_not_widened(self):
        """Rendered trust_required must not be weaker than what the manifest specifies."""
        _TRUST_ORDER = {"trusted": 2, "conditional": 1, "untrusted": 0}
        m = _manifest([_entry("fs_read", ["repo://local/*"], trust_required="trusted")])
        tool = render_tools(m)[0]
        manifest_trust = m["allowed_actions"][0]["trust_required"]
        # rendered trust must be >= manifest trust (not widened / weakened)
        assert _TRUST_ORDER[tool.trust_required] >= _TRUST_ORDER[manifest_trust]

    def test_large_manifest_count_preserved(self):
        entries = [_entry(f"tool_{i}", [f"repo://local/path_{i}/*"]) for i in range(10)]
        m = _manifest(entries)
        assert len(render_tools(m)) == 10


# ---------------------------------------------------------------------------
# Integration: render from a compile_manifest output
# ---------------------------------------------------------------------------

class TestRenderFromCompiledManifest:
    """Verify render_tools works correctly on manifests produced by compile_manifest."""

    def test_render_from_compiled_manifest(self, repo_root):
        """Render tools from a real compiled manifest derived from the benign trace."""
        from pathlib import Path
        from awc.compiler.profiler import derive_profile
        from awc.compiler.compile_manifest import compile_manifest

        trace = repo_root / "fixtures" / "traces" / "benign_repo_maintenance.json"
        profile = derive_profile([trace], profile_id="test_render")
        manifest = compile_manifest(profile, manifest_id="test-render")

        tools = render_tools(manifest)

        # Must have exactly as many tools as allowed_actions
        assert len(tools) == len(manifest["allowed_actions"])

    def test_no_denied_tools_in_rendered_output(self, repo_root):
        from pathlib import Path
        from awc.compiler.profiler import derive_profile
        from awc.compiler.compile_manifest import compile_manifest

        trace = repo_root / "fixtures" / "traces" / "benign_repo_maintenance.json"
        profile = derive_profile([trace], profile_id="test_render2")
        manifest = compile_manifest(profile, manifest_id="test-render2")

        tools = render_tools(manifest)
        denied_actions = {e["action"] for e in manifest.get("denied_actions", [])}
        rendered_base_tools = {t.base_tool for t in tools}

        # No rendered tool should correspond to a denied action
        assert not (rendered_base_tools & denied_actions)

    def test_rendered_tools_preserve_resource_patterns(self, repo_root):
        from pathlib import Path
        from awc.compiler.profiler import derive_profile
        from awc.compiler.compile_manifest import compile_manifest

        trace = repo_root / "fixtures" / "traces" / "benign_repo_maintenance.json"
        profile = derive_profile([trace], profile_id="test_render3")
        manifest = compile_manifest(profile, manifest_id="test-render3")

        tools = render_tools(manifest)

        # Every rendered tool's resource patterns must appear in the manifest entry
        manifest_patterns_by_action: dict[str, list[list[str]]] = {}
        for entry in manifest["allowed_actions"]:
            manifest_patterns_by_action.setdefault(entry["action"], []).append(
                entry["permitted_resources"]
            )

        for tool in tools:
            valid_patterns = manifest_patterns_by_action.get(tool.base_tool, [])
            assert list(tool.allowed_resource_patterns) in valid_patterns
