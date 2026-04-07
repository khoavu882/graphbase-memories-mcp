from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GRAPHBASE_")

    backend: str = "neo4j"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("graphbase")
    neo4j_database: str = "neo4j"
    neo4j_max_pool_size: int = 10  # S-3: safe for Community single-node
    neo4j_connection_timeout: float = 5.0  # S-3

    retrieval_timeout_s: float = 5.0  # FR-23
    retrieval_max_retries: int = 1  # FR-24
    write_max_retries: int = 1  # FR-52
    governance_token_ttl_s: int = 60  # GovernanceToken expiry


settings = Settings()
