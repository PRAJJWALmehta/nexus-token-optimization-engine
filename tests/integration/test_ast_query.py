from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from src.app import create_app

# Dummy Graphify JSON structure to mock
_DUMMY_GRAPH = {
    "directed": False,
    "multigraph": False,
    "graph": {},
    "nodes": [
        {
            "id": "file_a",
            "label": "file_a.py",
            "file_type": "code",
            "source_file": "file_a.py",
            "source_location": "L1",
            "community": 0,
            "norm_label": "file_a.py"
        },
        {
            "id": "file_a_func1",
            "label": "func1()",
            "file_type": "code",
            "source_file": "file_a.py",
            "source_location": "L3",
            "community": 0,
            "norm_label": "func1()"
        },
        {
            "id": "file_b_func2",
            "label": "func2()",
            "file_type": "code",
            "source_file": "file_b.py",
            "source_location": "L2",
            "community": 0,
            "norm_label": "func2()"
        },
        {
            "id": "file_c_func3",
            "label": "func3()",
            "file_type": "code",
            "source_file": "file_c.py",
            "source_location": "L5",
            "community": 0,
            "norm_label": "func3()"
        }
    ],
    "links": [
        {
            "relation": "contains",
            "context": "definition",
            "confidence": "EXTRACTED",
            "source_file": "file_a.py",
            "source_location": "L3",
            "source": "file_a",
            "target": "file_a_func1"
        },
        {
            "relation": "calls",
            "context": "call",
            "confidence": "EXTRACTED",
            "source_file": "file_a.py",
            "source_location": "L4",
            "source": "file_a_func1",
            "target": "file_b_func2"
        },
        {
            "relation": "calls",
            "context": "call",
            "confidence": "EXTRACTED",
            "source_file": "file_b.py",
            "source_location": "L3",
            "source": "file_b_func2",
            "target": "file_c_func3"
        }
    ]
}


@patch("src.ast_extractor.storage.GraphifyStorageAdapter.load_graph")
def test_ast_query_success(mock_load_graph):
    mock_load_graph.return_value = _DUMMY_GRAPH
    app = create_app()

    with TestClient(app) as client:
        # Query depth=1 from file_a_func1
        resp = client.get("/api/ast/query?node_id=file_a_func1&depth=1")
        assert resp.status_code == 200
        data = resp.json()

        node_ids = {n["id"] for n in data["nodes"]}
        # Should contain starting node and depth 1 targets (file_b_func2)
        assert "file_a_func1" in node_ids
        assert "file_b_func2" in node_ids
        assert "file_c_func3" not in node_ids

        links = data["links"]
        assert len(links) == 1
        assert links[0]["source"] == "file_a_func1"
        assert links[0]["target"] == "file_b_func2"


@patch("src.ast_extractor.storage.GraphifyStorageAdapter.load_graph")
def test_ast_query_deeper(mock_load_graph):
    mock_load_graph.return_value = _DUMMY_GRAPH
    app = create_app()

    with TestClient(app) as client:
        # Query depth=2 from file_a_func1 (should reach file_c_func3)
        resp = client.get("/api/ast/query?node_id=file_a_func1&depth=2")
        assert resp.status_code == 200
        data = resp.json()

        node_ids = {n["id"] for n in data["nodes"]}
        assert "file_a_func1" in node_ids
        assert "file_b_func2" in node_ids
        assert "file_c_func3" in node_ids

        assert len(data["links"]) == 2


@patch("src.ast_extractor.storage.GraphifyStorageAdapter.load_graph")
def test_ast_query_not_found(mock_load_graph):
    mock_load_graph.return_value = _DUMMY_GRAPH
    app = create_app()

    with TestClient(app) as client:
        resp = client.get("/api/ast/query?node_id=non_existent")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
