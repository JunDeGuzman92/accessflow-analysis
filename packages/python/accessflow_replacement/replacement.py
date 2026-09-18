"""Single source-traceable edge replacement-path calculations."""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from packages.python.accessflow_graph.network import GraphBuild, GraphEdge


@dataclass(frozen=True)
class EdgeReplacement:
    restriction_id: str
    source_segment_id: str
    edge_id: str
    match_type: str
    evidence_confidence: str
    original_edge_length_m: float
    evaluation_state: str
    replacement_path_exists: bool | None
    replacement_distance_m: float | None
    added_replacement_distance_m: float | None
    replacement_ratio: float | None
    local_connectivity_lost: bool | None
    graph_component_id: int | None
    limitations: tuple[str, ...]


def _component_ids(graph: nx.MultiGraph) -> dict[str, int]:
    return {node: index for index, component in enumerate(nx.connected_components(graph)) for node in component}


def evaluate_edge(
    build: GraphBuild,
    edge: GraphEdge,
    *,
    restriction_id: str,
    match_type: str,
    evidence_confidence: str,
) -> EdgeReplacement:
    """Remove exactly one graph edge and reconnect its original endpoints if possible."""
    if build.metric_crs != "EPSG:26917":
        raise ValueError("replacement-path metrics require EPSG:26917")
    component_id = _component_ids(build.graph).get(edge.u)
    graph = build.graph.copy()
    graph.remove_edge(edge.u, edge.v, key=edge.edge_id)
    try:
        replacement = float(nx.shortest_path_length(graph, edge.u, edge.v, weight="weight"))
    except nx.NetworkXNoPath:
        return EdgeReplacement(
            restriction_id, edge.source_segment_id, edge.edge_id, match_type, evidence_confidence,
            edge.length_m, "EVALUATED", False, None, None, None, True, component_id,
            ("GEOMETRY_DERIVED_CITY_ROUTING_TOPOLOGY_NOT_AVAILABLE",),
        )
    return EdgeReplacement(
        restriction_id, edge.source_segment_id, edge.edge_id, match_type, evidence_confidence,
        edge.length_m, "EVALUATED", True, replacement, replacement - edge.length_m,
        replacement / edge.length_m if edge.length_m else None, False, component_id,
        ("GEOMETRY_DERIVED_CITY_ROUTING_TOPOLOGY_NOT_AVAILABLE",),
    )