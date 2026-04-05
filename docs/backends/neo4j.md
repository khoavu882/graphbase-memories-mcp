# Neo4j Backend

Graph-native storage using Cypher queries and Lucene full-text search. Useful for large projects where N-hop traversal performance matters.

## Requirements

- Docker (recommended) or a local Neo4j 5.x installation
- `neo4j` Python driver: `pip install graphbase-memories-mcp[neo4j]`

## Start Neo4j

```bash
# Using the project Makefile
make neo4j-up

# Or manually
docker run -d --name graphbase-neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/graphbase \
  neo4j:5-community
```

## Configuration

```bash
export GRAPHBASE_BACKEND=neo4j
export GRAPHBASE_NEO4J_URI=bolt://localhost:7687
export GRAPHBASE_NEO4J_USER=neo4j
export GRAPHBASE_NEO4J_PASSWORD=graphbase
```

Or in Claude Code `settings.json`:
```json
{
  "env": {
    "GRAPHBASE_BACKEND": "neo4j",
    "GRAPHBASE_NEO4J_URI": "bolt://localhost:7687",
    "GRAPHBASE_NEO4J_USER": "neo4j",
    "GRAPHBASE_NEO4J_PASSWORD": "graphbase"
  }
}
```

## When to use Neo4j

| Use SQLite | Use Neo4j |
|---|---|
| < 10,000 memories | > 10,000 memories |
| Single machine | Multi-machine or team shared instance |
| Zero extra deps | N-hop traversal performance critical |
| Prototype / personal | Production team setup |

## Switching backends

Data is not automatically migrated when switching backends. To move data:

```bash
# Export from SQLite
GRAPHBASE_BACKEND=sqlite graphbase-memories export --project my-project --output export.json

# Import into Neo4j
GRAPHBASE_BACKEND=neo4j graphbase-memories import --file export.json --merge
```
