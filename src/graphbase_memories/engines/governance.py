"""GovernanceEngine — token creation for global-scope write approval (FR-55, S-1)."""

from __future__ import annotations

from neo4j import AsyncDriver

from graphbase_memories.config import settings
from graphbase_memories.graph.models import GovernanceTokenNode
from graphbase_memories.graph.repositories import token_repo


async def create_token(
    content_preview: str,
    driver: AsyncDriver,
    database: str = "neo4j",
) -> GovernanceTokenNode:
    """Create and persist a one-time governance token for global writes.

    Delegates to token_repo with the TTL from settings. The returned node
    carries the token id and expiry — the MCP adapter formats these for the
    caller and adds protocol-level instructions.
    """
    return await token_repo.create(
        content_preview=content_preview,
        ttl_s=settings.governance_token_ttl_s,
        driver=driver,
        database=database,
    )
