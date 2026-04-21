"""
Domain layer — shared enums, result types, and input artifacts.

This package owns the core business types that are shared between the engine
layer and any adapter layer (MCP, REST, CLI). Adapters import from here and
extend as needed; engines import only from here, never from adapter packages.
"""
