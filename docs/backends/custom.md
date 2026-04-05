# Custom Backend

Implement your own storage backend by subclassing `GraphEngine`.

## 1. Implement the ABC

```python
from graphbase_memories.graph.engine import (
    GraphEngine, MemoryNode, EntityNode, Edge,
    BlastRadiusResult, GraphData
)

class MyBackend(GraphEngine):
    def __init__(self, config, project: str):
        self._project = project

    def store_memory_with_entities(self, memory, entity_names, entity_type="concept"):
        ...  # implement all 20 abstract methods

    # ... etc
```

All 20 abstract methods must be implemented. The ABC is in `src/graphbase_memories/graph/engine.py`.

## 2. Register via entry_points

In your package's `pyproject.toml`:

```toml
[project.entry-points."graphbase_memories.backends"]
mybackend = "mypackage.backend:MyBackend"
```

Install your package:
```bash
pip install -e .
```

## 3. Use it

```bash
GRAPHBASE_BACKEND=mybackend graphbase-memories server
```

graphbase-memories will discover your backend via `importlib.metadata.entry_points` and load it automatically. No changes to the core package needed.

## Constructor contract

Your class must accept `(config: Config, project: str)` as positional arguments:

```python
def __init__(self, config: "graphbase_memories.config.Config", project: str):
    ...
```

`config.data_dir` gives you the root data directory. `project` is the slug.

## Key design constraints from the ABC

- `store_memory_with_entities` is the only write entry point for the tool layer
- `include_deleted=False` is the default for all read methods
- `search_memories` must exclude soft-deleted memories regardless of `include_deleted`
- `link_entities` is idempotent — `(from_id, to_id, edge_type)` must be unique
- `get_graph_data` must populate `memory_entity_links` in the returned `GraphData`

Run the contract test suite against your backend:

```bash
GRAPHBASE_BACKEND=mybackend pytest tests/test_sqlite_contract.py -v
```

The contract tests are backend-agnostic and test all 20 methods via the ABC interface.
