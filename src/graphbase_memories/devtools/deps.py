"""FastAPI dependency injection for the devtools HTTP server."""

from typing import Annotated

from fastapi import Depends, Request
from neo4j import AsyncDriver


def get_driver(request: Request) -> AsyncDriver:
    """Return the Neo4j async driver from application state.

    Enables dependency_overrides[get_driver] in tests without module-level
    monkeypatching.
    """
    return request.app.state.driver


DriverDep = Annotated[AsyncDriver, Depends(get_driver)]
