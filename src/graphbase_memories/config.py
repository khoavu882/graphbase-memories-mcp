from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GRAPHBASE_")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("graphbase")
    neo4j_database: str = "neo4j"
    # Pool budget: MCP server uses this pool (default 10), devtools server uses a
    # separate hard-capped pool of 2 (see devtools/server.py:_DEVTOOLS_POOL_SIZE).
    # Combined ceiling = 12, which fits comfortably within Neo4j Community Edition's
    # default of 100 simultaneous connections. Raise here only if you also raise
    # _DEVTOOLS_POOL_SIZE so both processes stay within the available budget.
    neo4j_max_pool_size: int = 10
    neo4j_connection_timeout: float = 5.0

    retrieval_timeout_s: float = 5.0  # FR-23
    retrieval_max_retries: int = 1  # FR-24
    retrieval_focus_limit: int = 10  # GRAPHBASE_RETRIEVAL_FOCUS_LIMIT
    retrieval_project_limit: int = 20  # GRAPHBASE_RETRIEVAL_PROJECT_LIMIT
    retrieval_global_limit: int = 5  # GRAPHBASE_RETRIEVAL_GLOBAL_LIMIT
    write_max_retries: int = 1  # FR-52
    governance_token_ttl_s: int = 60  # GovernanceToken expiry

    federation_active_window_minutes: int = 60  # GRAPHBASE_FEDERATION_ACTIVE_WINDOW_MINUTES
    federation_max_results: int = 100  # GRAPHBASE_FEDERATION_MAX_RESULTS
    impact_max_depth: int = 3  # GRAPHBASE_IMPACT_MAX_DEPTH
    workspace_enforce_isolation: bool = True  # GRAPHBASE_WORKSPACE_ENFORCE_ISOLATION

    fts_enabled: bool = True  # GRAPHBASE_FTS_ENABLED — toggle for envs without FTS indexes
    fts_limit: int = 20  # GRAPHBASE_FTS_LIMIT — BM25 candidates per fulltext index
    rrf_k: int = 60  # GRAPHBASE_RRF_K — RRF damping constant

    freshness_recent_days: int = 7  # GRAPHBASE_FRESHNESS_RECENT_DAYS
    freshness_stale_days: int = 30  # GRAPHBASE_FRESHNESS_STALE_DAYS


settings = Settings()
