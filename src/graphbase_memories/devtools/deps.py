"""FastAPI dependency injection for the devtools HTTP server."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from neo4j import AsyncDriver

_DEVTOOLS_TOKEN: str | None = None


def get_driver(request: Request) -> AsyncDriver:
    """Return the Neo4j async driver from application state.

    Enables dependency_overrides[get_driver] in tests without module-level
    monkeypatching.
    """
    return request.app.state.driver


def set_devtools_token(token: str) -> None:
    """Store the current devtools write token for request validation."""
    global _DEVTOOLS_TOKEN
    _DEVTOOLS_TOKEN = token


def get_devtools_token() -> str | None:
    """Return the current devtools write token."""
    return _DEVTOOLS_TOKEN


def require_token(
    x_devtools_token: Annotated[str | None, Header(alias="X-Devtools-Token")] = None,
) -> str:
    """Validate the startup-generated devtools write token."""
    if not _DEVTOOLS_TOKEN or x_devtools_token != _DEVTOOLS_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid or missing devtools token")
    return x_devtools_token


DriverDep = Annotated[AsyncDriver, Depends(get_driver)]
DevtoolsTokenDep = Annotated[str, Depends(require_token)]
