"""awc.observe – Stage 1 of the Agent World Compiler pipeline.

Records agent tool calls into the trace format consumed by the profiler.
"""

from awc.observe.recorder import TraceRecorder

__all__ = ["TraceRecorder"]
