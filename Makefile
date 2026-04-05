.PHONY: test neo4j-up neo4j-down neo4j-test neo4j-logs

# ── SQLite tests (no Docker needed) ──────────────────────────────────────────

test:
	uv run pytest tests/ -v --ignore=tests/neo4j

test-cov:
	uv run pytest tests/ --ignore=tests/neo4j \
	  --cov=src/graphbase_memories --cov-report=term-missing

# ── Neo4j local Docker ────────────────────────────────────────────────────────

neo4j-up:
	docker compose -f docker-compose.neo4j.yml up -d --wait
	@echo "Neo4j is healthy at bolt://localhost:7687  (browser: http://localhost:7474)"

neo4j-down:
	docker compose -f docker-compose.neo4j.yml down

neo4j-logs:
	docker compose -f docker-compose.neo4j.yml logs --tail=50 neo4j

# Run contract tests against live Neo4j (starts/stops Docker automatically)
neo4j-test: neo4j-up
	GRAPHBASE_NEO4J_PASSWORD=graphbase uv run pytest tests/neo4j/ -v
	$(MAKE) neo4j-down

# Run ALL tests (SQLite + Neo4j); keeps Docker running on failure for inspection
neo4j-test-full: neo4j-up
	GRAPHBASE_NEO4J_PASSWORD=graphbase uv run pytest tests/ -v; \
	  status=$$?; \
	  $(MAKE) neo4j-down; \
	  exit $$status