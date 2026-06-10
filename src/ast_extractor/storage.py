"""Graphify Storage Adapter.

Manages loading, updating, and saving the local Graphify knowledge graph file.
Ensures that updates to a file cleanly replace old nodes/edges to prevent graph drift.
"""

import json
import os


class GraphifyStorageAdapter:
    """Adapter to read and write to the local Graphify JSON graph storage."""

    def __init__(self, graph_path: str = "graphify-out/graph.json"):
        self.graph_path = graph_path

    def load_graph(self) -> dict:
        """Load the Graphify JSON graph from disk.

        Returns
        -------
        dict
            The parsed graph structure, or a default empty graph format if not found.
        """
        if not os.path.exists(self.graph_path):
            return {
                "directed": False,
                "multigraph": False,
                "graph": {},
                "nodes": [],
                "links": []
            }

        try:
            with open(self.graph_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # Fallback if corrupt
            return {
                "directed": False,
                "multigraph": False,
                "graph": {},
                "nodes": [],
                "links": []
            }

    def save_graph(self, graph_data: dict) -> None:
        """Save the Graphify JSON graph back to disk.

        Parameters
        ----------
        graph_data : dict
            The graph dictionary to serialize.
        """
        os.makedirs(os.path.dirname(self.graph_path), exist_ok=True)
        try:
            with open(self.graph_path, "w", encoding="utf-8") as f:
                json.dump(graph_data, f, indent=2)
        except Exception as exc:
            raise RuntimeError(f"Failed to write Graphify storage: {exc}")

    def update_graph_for_file(self, file_path: str, file_graph: dict) -> None:
        """Update nodes and links in the graph for a specific file path.

        Purges all existing nodes and links originating from `file_path`
        and inserts the newly extracted ones.

        Parameters
        ----------
        file_path : str
            The workspace-relative file path that was updated.
        file_graph : dict
            Contains the new "nodes" and "links" extracted from the file.
        """
        graph = self.load_graph()

        # Build list of new node IDs to help filter out connections/nodes
        new_nodes = file_graph.get("nodes", [])
        new_links = file_graph.get("links", [])
        new_node_ids = {n["id"] for n in new_nodes}

        # 1. Purge old nodes associated with this file_path or matching new node IDs
        old_nodes = graph.get("nodes", [])
        updated_nodes = [
            n for n in old_nodes
            if n.get("source_file") != file_path and n.get("id") not in new_node_ids
        ]
        # Append new nodes
        updated_nodes.extend(new_nodes)

        # 2. Purge old links associated with this file_path or referencing any purged node IDs
        old_links = graph.get("links", [])
        updated_links = [
            link for link in old_links
            if link.get("source_file") != file_path
            and link.get("source") not in new_node_ids
            and link.get("target") not in new_node_ids
        ]
        # Append new links
        # Filter duplicates just in case
        seen_links = set()
        for link in new_links:
            key = (link["source"], link["target"], link.get("relation"))
            if key not in seen_links:
                seen_links.add(key)
                updated_links.append(link)

        # Update and save
        graph["nodes"] = updated_nodes
        graph["links"] = updated_links
        self.save_graph(graph)
