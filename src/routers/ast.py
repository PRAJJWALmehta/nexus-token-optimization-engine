"""AST router.

Exposes endpoints for querying the extracted AST graph.
"""

import time
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from src.ast_extractor.storage import GraphifyStorageAdapter
from src.telemetry import ast_queries_total, ast_query_latency_seconds

router = APIRouter(prefix="/api/ast", tags=["ast"])


@router.get("/query", response_class=JSONResponse)
async def query_ast(
    node_id: str = Query(..., description="The starting node ID to query dependencies for"),
    depth: int = Query(2, ge=1, le=10, description="Max depth to traverse outgoing dependencies")
) -> dict:
    """Query AST dependency subgraph starting from a given node ID.

    Parameters
    ----------
    node_id : str
        The identifier of the node to start traversal from.
    depth : int
        Maximum recursion depth to traverse dependencies.

    Returns
    -------
    dict
        A subgraph containing "nodes" and "links" matching the queried dependency tree.
    """
    start_time = time.perf_counter()
    status = "success"
    try:
        adapter = GraphifyStorageAdapter()
        graph = adapter.load_graph()

        # Create mapping of all nodes for quick lookup
        nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}
        if node_id not in nodes_by_id:
            status = "not_found"
            raise HTTPException(
                status_code=404,
                detail=f"Node '{node_id}' not found in the local AST graph."
            )

        # Map outgoing links by source ID to trace outgoing dependencies
        links_by_source = {}
        for link in graph.get("links", []):
            source = link.get("source")
            if source not in links_by_source:
                links_by_source[source] = []
            links_by_source[source].append(link)

        visited_nodes = {node_id}
        collected_links = []
        queue = [(node_id, 0)]

        while queue:
            curr_id, curr_depth = queue.pop(0)
            if curr_depth >= depth:
                continue

            outgoing = links_by_source.get(curr_id, [])
            for link in outgoing:
                target_id = link.get("target")
                if target_id and target_id in nodes_by_id:
                    collected_links.append(link)
                    if target_id not in visited_nodes:
                        visited_nodes.add(target_id)
                        queue.append((target_id, curr_depth + 1))

        subgraph_nodes = [nodes_by_id[nid] for nid in visited_nodes]

        return {
            "nodes": subgraph_nodes,
            "links": collected_links
        }
    except HTTPException:
        raise
    except Exception:
        status = "error"
        raise
    finally:
        ast_queries_total.labels(status=status).inc()
        ast_query_latency_seconds.observe(time.perf_counter() - start_time)

