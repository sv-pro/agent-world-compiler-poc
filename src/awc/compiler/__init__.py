"""
compiler package: profile derivation, manifest compilation, and tool rendering.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from awc.compiler.profiler import CapabilityProfile, derive_profile
    from awc.compiler.compile_manifest import compile_manifest
    from awc.compiler.render_tools import RenderedTool, render_tools


def __getattr__(name: str):
    if name in ("CapabilityProfile", "derive_profile"):
        from awc.compiler.profiler import CapabilityProfile, derive_profile
        return {"CapabilityProfile": CapabilityProfile, "derive_profile": derive_profile}[name]
    if name == "compile_manifest":
        from awc.compiler.compile_manifest import compile_manifest
        return compile_manifest
    if name in ("RenderedTool", "render_tools"):
        from awc.compiler.render_tools import RenderedTool, render_tools
        return {"RenderedTool": RenderedTool, "render_tools": render_tools}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
