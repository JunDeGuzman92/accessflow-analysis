"""Restriction candidate-set removal metrics without invented external OD pairs."""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from packages.python.accessflow_graph.network import GraphBuild, GraphEdge


@dataclass(frozen=True)
class RestrictionSetImpact:
    restriction_id: str
    evaluation_state: str
    removed_edge_count: int
    boundary_node_count: int
    connected_boundary_pair_count: int
    disconnected_boundary_pair_count: int
    component_increase: int | None
    limitations: tuple[str, ...]


def evaluate_edge_set(build: GraphBuild, restriction_id: str, edges: list[GraphEdge]) -> RestrictionSetImpact:
    """Remove an evidence scenario's edges and assess only formerly connected boundary-node pairs."""
    if not edges:
        return RestrictionSetImpact(restriction_id, "INSUFFICIENT_EVIDENCE", 0, 0, 0, 0, None, ("NO_CANDIDATE_EDGE",))
    graph = build.graph
    baseline_components = nx.number_connected_components(graph)
    boundary = sorted({node for edge in edges for node in (edge.u, edge.v)})
    removed = graph.copy()
    removed.remove_edges_from((edge.u, edge.v, edge.edge_id) for edge in edges)
    connected = disconnected = 0
    for index, left in enumerate(boundary):
        for right in boundary[index + 1:]:
            if nx.has_path(graph, left, right):
                if nx.has_path(removed, left, right):
                    connected += 1
                else:
                    disconnected += 1
    return RestrictionSetImpact(
        restriction_id, "EVALUATED", len(edges), len(boundary), connected, disconnected,
        nx.number_connected_components(removed) - baseline_components,
        ("BOUNDARY_NODE_RELATIONSHIPS_ONLY", "GEOMETRY_DERIVED_CITY_ROUTING_TOPOLOGY_NOT_AVAILABLE"),
    )