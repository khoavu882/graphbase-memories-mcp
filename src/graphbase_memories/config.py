import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_data_dir() -> Path:
    """
    Resolve the Graphbase data directory.

    Priority:
      1. GRAPHBASE_DATA_DIR env var (explicit override)
      2. ~/.graphbase (default)
    """
    explicit = os.getenv("GRAPHBASE_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser()
    return Path("~/.graphbase").expanduser()


@dataclass
class Config:
    backend: str = field(
        default_factory=lambda: os.getenv("GRAPHBASE_BACKEND", "sqlite")
    )
    data_dir: Path = field(default_factory=_default_data_dir)
    log_level: str = field(
        default_factory=lambda: os.getenv("GRAPHBASE_LOG_LEVEL", "WARNING")
    )
    log_to_file: bool = True

    # Neo4j connection (v2 only — ignored when backend=sqlite)
    neo4j_uri: str = field(
        default_factory=lambda: os.getenv("GRAPHBASE_NEO4J_URI", "bolt://localhost:7687")
    )
    neo4j_user: str = field(
        default_factory=lambda: os.getenv("GRAPHBASE_NEO4J_USER", "neo4j")
    )
    neo4j_password: str | None = field(
        default_factory=lambda: os.getenv("GRAPHBASE_NEO4J_PASSWORD")
    )

    def project_dir(self, project: str) -> Path:
        p = self.data_dir / project
        p.mkdir(parents=True, exist_ok=True)
        return p

    def db_path(self, project: str) -> Path:
        return self.project_dir(project) / "memories.db"

    def log_path(self, project: str) -> Path:
        return self.project_dir(project) / "graphbase.log"
