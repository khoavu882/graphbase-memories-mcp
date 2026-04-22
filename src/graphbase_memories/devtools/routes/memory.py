"""Memory inspection routes — list, get, search, and relationship traversal."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from graphbase_memories.config import settings
from graphbase_memories.devtools.deps import DevtoolsTokenDep, DriverDep

router = APIRouter(tags=["memory"])

_ALLOWED_LABELS = {"Session", "Decision", "Pattern", "Context", "EntityFact"}
_ALLOWED_FORMATS = {"list", "timeline"}
_ALLOWED_SORT_FIELDS = {
    "created_at": "n.created_at",
    "title": "coalesce(n.title, '')",
    "entity_name": "coalesce(n.entity_name, '')",
}
_ALLOWED_PATCH_FIELDS = {"title", "content", "summary", "fact"}


def _validate_label(label: str | None) -> str | None:
    if label is not None and label not in _ALLOWED_LABELS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid label {label!r}. Must be one of: {sorted(_ALLOWED_LABELS)}",
        )
    return label


def _validate_labels(labels: list[str] | None) -> list[str] | None:
    if labels is None:
        return None
    invalid = sorted(set(labels) - _ALLOWED_LABELS)
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid labels {invalid!r}. Must be drawn from: {sorted(_ALLOWED_LABELS)}",
        )
    return labels


def _invalid_labels(labels: list[str] | None) -> list[str]:
    if labels is None:
        return []
    return sorted(set(labels) - _ALLOWED_LABELS)


def _validate_sort(sort_by: str, sort_order: str) -> tuple[str, str]:
    if sort_by not in _ALLOWED_SORT_FIELDS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid sort_by {sort_by!r}. Must be one of: {sorted(_ALLOWED_SORT_FIELDS)}",
        )
    if sort_order not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="sort_order must be 'asc' or 'desc'")
    return _ALLOWED_SORT_FIELDS[sort_by], sort_order.upper()


def _validate_format(response_format: str) -> str:
    if response_format not in _ALLOWED_FORMATS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid format {response_format!r}. Must be one of: {sorted(_ALLOWED_FORMATS)}",
        )
    return response_format


def _timeline_date(created_at: str | None) -> str:
    if not created_at:
        return "unknown"
    return created_at.split("T", 1)[0]


def _build_timeline_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for item in items:
        date_key = _timeline_date(item.get("created_at"))
        if not groups or groups[-1]["date"] != date_key:
            groups.append({"date": date_key, "count": 0, "items": []})
        groups[-1]["items"].append(item)
        groups[-1]["count"] += 1
    return groups


def _shape_memory_response(
    items: list[dict[str, Any]],
    total: int,
    response_format: str,
) -> dict[str, Any]:
    if response_format == "timeline":
        return {
            "format": "timeline",
            "items": items,
            "groups": _build_timeline_groups(items),
            "total": total,
        }
    return {"items": items, "total": total}


@router.get("/memory")
async def list_memory(
    driver: DriverDep,
    project_id: Annotated[str | None, Query()] = None,
    label: Annotated[
        str | None,
        Query(
            description="Node label filter — one of: Session, Decision, Pattern, Context, EntityFact"
        ),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort_by: Annotated[str, Query()] = "created_at",
    sort_order: Annotated[str, Query()] = "desc",
    since_days: Annotated[int | None, Query(ge=0)] = None,
    format: Annotated[str, Query()] = "list",
):
    """List recent memory nodes, optionally filtered by project and label."""
    label = _validate_label(label)
    order_expr, order_direction = _validate_sort(sort_by, sort_order)
    response_format = _validate_format(format)
    label_clause = "AND $label IN labels(n)" if label else ""
    project_clause = (
        'AND EXISTS { MATCH (n)-[rel]->(:Project {id: $pid}) WHERE type(rel) = "BELONGS_TO" }'
        if project_id
        else ""
    )
    since_clause = (
        "AND n.created_at > datetime() - duration({days: $since_days})"
        if since_days is not None
        else ""
    )
    base_where = f"""
        WHERE any(lbl IN labels(n) WHERE lbl IN $allowed_labels)
        {label_clause}
        {project_clause}
        {since_clause}
    """
    async with driver.session(database=settings.neo4j_database) as session:
        params = {
            "allowed_labels": sorted(_ALLOWED_LABELS),
            "label": label,
            "pid": project_id,
            "limit": limit,
            "offset": offset,
            "since_days": since_days,
        }
        result = await session.run(
            f"""
            MATCH (n)
            {base_where}
            RETURN n {{.*, created_at: toString(n.created_at)}} AS node, labels(n)[0] AS label
            ORDER BY {order_expr} {order_direction}
            SKIP $offset
            LIMIT $limit
            """,
            **params,
        )
        nodes = []
        async for r in result:
            item = dict(r["node"])
            item["_label"] = r["label"]
            nodes.append(item)
        total_result = await session.run(
            f"""
            MATCH (n)
            {base_where}
            RETURN count(n) AS total
            """,
            **params,
        )
        total_record = await total_result.single()
    return _shape_memory_response(
        nodes, total_record["total"] if total_record else 0, response_format
    )


@router.get("/memory/{node_id}/relationships")
async def node_relationships(node_id: str, driver: DriverDep):
    """Return incoming and outgoing relationships for any memory node."""
    async with driver.session(database=settings.neo4j_database) as session:
        node_result = await session.run(
            "MATCH (n {id: $id}) RETURN n {.*} AS node, labels(n)[0] AS label LIMIT 1",
            id=node_id,
        )
        record = await node_result.single()
        if not record:
            raise HTTPException(status_code=404, detail=f"Node {node_id!r} not found")
        node_data = dict(record["node"])
        node_data["_label"] = record["label"]

        out_result = await session.run(
            """
            MATCH (n {id: $id})-[r]->(m)
            RETURN type(r) AS rel_type, m.id AS to_id,
                   labels(m)[0] AS to_label, m.title AS to_title
            LIMIT 50
            """,
            id=node_id,
        )
        outgoing = [
            {
                "to_id": r["to_id"],
                "to_label": r["to_label"],
                "type": r["rel_type"],
                "to_title": r["to_title"],
            }
            async for r in out_result
        ]

        in_result = await session.run(
            """
            MATCH (m)-[r]->(n {id: $id})
            RETURN type(r) AS rel_type, m.id AS from_id,
                   labels(m)[0] AS from_label, m.title AS from_title
            LIMIT 50
            """,
            id=node_id,
        )
        incoming = [
            {
                "from_id": r["from_id"],
                "from_label": r["from_label"],
                "type": r["rel_type"],
                "from_title": r["from_title"],
            }
            async for r in in_result
        ]

    return {"node": node_data, "outgoing": outgoing, "incoming": incoming}


@router.get("/memory/{node_id}")
async def get_node(node_id: str, driver: DriverDep):
    """Get a single memory node by id."""
    async with driver.session(database=settings.neo4j_database) as session:
        result = await session.run(
            "MATCH (n {id: $id}) RETURN n {.*} AS node, labels(n)[0] AS label LIMIT 1",
            id=node_id,
        )
        record = await result.single()
        if not record:
            raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
        item = dict(record["node"])
        item["_label"] = record["label"]
        return item


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1)
    project_id: str | None = None
    label: str | None = None
    labels: list[str] | None = None
    limit: int = Field(default=20, ge=1, le=100)
    since_days: int | None = Field(default=None, ge=0)
    offset: int = Field(default=0, ge=0)
    sort_by: str = "created_at"
    sort_order: str = "desc"

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        query = v.strip()
        if not query:
            raise ValueError("query must contain non-whitespace text")
        return query

    @field_validator("label")
    @classmethod
    def validate_label(cls, v: str | None) -> str | None:
        invalid = _invalid_labels([v] if v is not None else None)
        if invalid:
            raise ValueError(f"Invalid label {v!r}. Must be one of: {sorted(_ALLOWED_LABELS)}")
        return v

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, v: list[str] | None) -> list[str] | None:
        invalid = _invalid_labels(v)
        if invalid:
            raise ValueError(
                f"Invalid labels {invalid!r}. Must be drawn from: {sorted(_ALLOWED_LABELS)}"
            )
        return v

    @field_validator("sort_by")
    @classmethod
    def validate_sort_by(cls, v: str) -> str:
        if v not in _ALLOWED_SORT_FIELDS:
            raise ValueError(f"Invalid sort_by {v!r}. Must be one of: {sorted(_ALLOWED_SORT_FIELDS)}")
        return v

    @field_validator("sort_order")
    @classmethod
    def validate_sort_order(cls, v: str) -> str:
        if v not in {"asc", "desc"}:
            raise ValueError("sort_order must be 'asc' or 'desc'")
        return v


@router.post("/memory/search")
async def search_memory(body: MemorySearchRequest, driver: DriverDep):
    """Full-text search across memory nodes using CONTAINS on content fields."""
    order_expr, order_direction = _validate_sort(body.sort_by, body.sort_order)
    filter_labels = body.labels or ([body.label] if body.label else None)
    _validate_labels(filter_labels)
    label_clause = "AND any(lbl IN labels(n) WHERE lbl IN $filter_labels)" if filter_labels else ""
    project_clause = (
        'AND EXISTS { MATCH (n)-[rel]->(:Project {id: $pid}) WHERE type(rel) = "BELONGS_TO" }'
        if body.project_id
        else ""
    )
    since_clause = (
        "AND n.created_at > datetime() - duration({days: $since_days})" if body.since_days else ""
    )
    text_predicate = """
        (
            n.content CONTAINS $search_text
            OR n.title CONTAINS $search_text
            OR n.summary CONTAINS $search_text
            OR n.entity_name CONTAINS $search_text
            OR n.fact CONTAINS $search_text
        )
    """
    async with driver.session(database=settings.neo4j_database) as session:
        params = {
            "search_text": body.query,
            "filter_labels": filter_labels,
            "pid": body.project_id,
            "since_days": body.since_days,
            "limit": body.limit,
            "offset": body.offset,
        }
        result = await session.run(
            f"""
            MATCH (n)
            WHERE {text_predicate}
            {project_clause}
            {label_clause}
            {since_clause}
            RETURN n {{.*, created_at: toString(n.created_at)}} AS node, labels(n)[0] AS label
            ORDER BY {order_expr} {order_direction}
            SKIP $offset
            LIMIT $limit
            """,
            **params,
        )
        nodes = []
        async for r in result:
            item = dict(r["node"])
            item["_label"] = r["label"]
            nodes.append(item)
        total_result = await session.run(
            f"""
            MATCH (n)
            WHERE {text_predicate}
            {project_clause}
            {label_clause}
            {since_clause}
            RETURN count(n) AS total
            """,
            **params,
        )
        total_record = await total_result.single()
    return {"items": nodes, "total": total_record["total"] if total_record else 0}


class MemoryPatchRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    summary: str | None = None
    fact: str | None = None

    def updates(self) -> dict[str, str | None]:
        return self.model_dump(exclude_unset=True)


class MemoryBulkDeleteRequest(BaseModel):
    ids: list[str]
    confirm: bool = False

    @field_validator("ids")
    @classmethod
    def validate_ids(cls, value: list[str]) -> list[str]:
        cleaned = []
        seen: set[str] = set()
        for raw_id in value:
            node_id = raw_id.strip()
            if not node_id or node_id in seen:
                continue
            seen.add(node_id)
            cleaned.append(node_id)
        if not cleaned:
            raise ValueError("ids must contain at least one node id")
        return cleaned


def _validate_patch_fields(payload: dict[str, Any]) -> dict[str, Any]:
    # Unknown fields (including structural ones like id, _label, created_at) are stripped
    # by Pydantic before this function is called, so only invalid allowed-looking keys
    # and empty-payload need to be handled here.
    invalid = sorted(set(payload) - _ALLOWED_PATCH_FIELDS)
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid patch fields: {invalid}. Allowed: {sorted(_ALLOWED_PATCH_FIELDS)}",
        )
    if not payload:
        raise HTTPException(
            status_code=422, detail="Patch body must contain at least one allowed field"
        )
    return payload


@router.patch("/memory/{node_id}")
async def patch_node(
    node_id: str,
    body: MemoryPatchRequest,
    driver: DriverDep,
    _: DevtoolsTokenDep,
):
    """Patch selected memory fields on a node."""
    updates = _validate_patch_fields(body.updates())
    async with driver.session(database=settings.neo4j_database) as session:
        result = await session.run(
            """
            MATCH (n {id: $id})
            SET n += $updates
            RETURN n {.*, created_at: toString(n.created_at)} AS node, labels(n)[0] AS label
            LIMIT 1
            """,
            id=node_id,
            updates=updates,
        )
        record = await result.single()
        if not record:
            raise HTTPException(status_code=404, detail=f"Node {node_id!r} not found")
        item = dict(record["node"])
        item["_label"] = record["label"]
        return item


@router.delete("/memory/{node_id}")
async def delete_node(
    node_id: str,
    driver: DriverDep,
    _: DevtoolsTokenDep,
    confirm: bool = Query(False),
):
    """Delete a memory node after explicit confirmation."""
    if not confirm:
        raise HTTPException(status_code=422, detail="confirm=true is required for deletion")
    async with driver.session(database=settings.neo4j_database) as session:
        check_result = await session.run(
            "MATCH (n {id: $id}) RETURN n.id AS id LIMIT 1", id=node_id
        )
        if await check_result.single() is None:
            raise HTTPException(status_code=404, detail=f"Node {node_id!r} not found")
        await session.run("MATCH (n {id: $id}) DETACH DELETE n", id=node_id)
    return {"deleted": True, "id": node_id}


@router.post("/memory/bulk-delete")
async def bulk_delete_nodes(
    body: MemoryBulkDeleteRequest,
    driver: DriverDep,
    _: DevtoolsTokenDep,
):
    """Delete multiple memory nodes in one request."""
    if not body.confirm:
        raise HTTPException(status_code=422, detail="confirm=true is required for bulk deletion")

    input_order = {node_id: index for index, node_id in enumerate(body.ids)}
    async with driver.session(database=settings.neo4j_database) as session:
        result = await session.run(
            "MATCH (n) WHERE n.id IN $ids RETURN n.id AS id",
            ids=body.ids,
        )
        found_ids = sorted(
            [record["id"] async for record in result],
            key=lambda node_id: input_order[node_id],
        )
        if found_ids:
            await session.run(
                "MATCH (n) WHERE n.id IN $ids DETACH DELETE n",
                ids=found_ids,
            )

    found_set = set(found_ids)
    missing_ids = [node_id for node_id in body.ids if node_id not in found_set]
    return {
        "deleted": found_ids,
        "missing": missing_ids,
        "deleted_count": len(found_ids),
    }
