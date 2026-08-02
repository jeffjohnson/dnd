"""Deterministic GUR -> GUP compiler for the AD&D 1e mechanical relationship graph.

Owned by the Builder role. See `agents/builder/INSTRUCTIONS.md`.
"""

from .compiler import TOOL_NAME, TOOL_VERSION, Compiler, CompileResult

__all__ = ["Compiler", "CompileResult", "TOOL_NAME", "TOOL_VERSION"]
