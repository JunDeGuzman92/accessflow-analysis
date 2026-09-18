"""Endpoint-derived pedestrian graph and disruption experiments."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Iterable

import networkx as nx
from shapely.geometry import LineString, MultiLineString, Point

from packages.python.accessflow_spatial.matching import (
    METRIC_CRS,
    NetworkSegment,
    load_network_segments,
    transform_geometries,
)


@dataclass(frozen=True)
class GraphEdge:
    edge_id: str
    source_segment_id: str
    part_index: int
    u: str
    v: str
    length_m: float
    geometry_metric: LineString


@dataclass(frozen=True)
class GraphBuild:
    graph: nx.MultiGraph
    edges: tuple[GraphEdge, ...]
    node_coordinates: dict[str, tuple[float, float]]
    endpoint_tolerance_m: float
    source_crs: str
    metric_crs: str


@dataclass(frozen=True)
class GraphAudit:
    endpoint_tolerance_m: float
    candidate_nodes: int
    candidate_edges: int
    connected_components: int
    largest_component_nodes: int
    isolated_nodes: int
    isolated_edges: int
    degree_distribution: dict[str, int]
    multipart_distribution: dict[int, int]
    endpoint_occurrence_distribution: dict[int, int]


def _parts(geometry: object) -> list[LineString]:
    if isinstance(geometry, LineString):
        return [geometry]
    if isinstance(geometry, MultiLineString):
        return list(geometry.geoms)
    raise ValueError(f"unsupported network geometry type: {geometry.geom_type}")


def _endpoint_clusters(points: list[tuple[float, float]], tolerance_m: float) -> list[int]:
    if tolerance_m < 0:
        raise ValueError("endpoint tolerance must be non-negative")
    parent = list(range(len(points)))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    if tolerance_m == 0:
        exact_points: dict[tuple[float, float], int] = {}
        for index, point in enumerate(points):
            other = exact_points.setdefault(point, index)
            union(index, other)
        return [find(index) for index in range(len(points))]
    cells: dict[tuple[int, int], list[int]] = {}
    for index, (x_coord, y_coord) in enumerate(points):
        cell = (math.floor(x_coord / tolerance_m), math.floor(y_coord / tolerance_m))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for other in cells.get((cell[0] + dx, cell[1] + dy), []):
                    ox, oy = points[other]
                    if math.hypot(x_coord - ox, y_coord - oy) <= tolerance_m:
                        union(index, other)
        cells.setdefault(cell, []).append(index)
    return [find(index) for index in range(len(points))]


def build_graph(segments: list[NetworkSegment], endpoint_tolerance_m: float = 0.0) -> GraphBuild:
    """Build an endpoint graph; crossings without shared endpoints remain disconnected."""
    projected = transform_geometries([segment.geometry_wgs84 for segment in segments])
    parts: list[tuple[str, int, LineString]] = []
    endpoints: list[tuple[float, float]] = []
    part_endpoint_indices: list[tuple[int, int]] = []
    for segment, geometry in zip(segments, projected):
        for part_index, line in enumerate(_parts(geometry)):
            if len(line.coords) < 2 or line.length <= 0:
                continue
            parts.append((segment.segment_id, part_index, line))
            start_index = len(endpoints)
            endpoints.extend([tuple(line.coords[0]), tuple(line.coords[-1])])
            part_endpoint_indices.append((start_index, start_index + 1))
    roots = _endpoint_clusters(endpoints, endpoint_tolerance_m)
    root_to_node: dict[int, str] = {}
    node_coordinates: dict[str, tuple[float, float]] = {}
    for index, root in enumerate(roots):
        node_id = root_to_node.setdefault(root, f"n{len(root_to_node):06d}")
        if node_id not in node_coordinates:
            node_coordinates[node_id] = endpoints[index]
    graph = nx.MultiGraph()
    graph.add_nodes_from(node_coordinates)
    graph_edges: list[GraphEdge] = []
    for edge_index, ((source_id, part_index, line), (start, end)) in enumerate(zip(parts, part_endpoint_indices)):
        u, v = root_to_node[roots[start]], root_to_node[roots[end]]
        edge_id = f"{source_id}:{part_index}"
        edge = GraphEdge(edge_id, source_id, part_index, u, v, float(line.length), line)
        graph.add_edge(u, v, key=edge_id, weight=edge.length_m, source_segment_id=source_id, geometry_metric=line)
        graph_edges.append(edge)
    return GraphBuild(graph, tuple(graph_edges), node_coordinates, endpoint_tolerance_m, "EPSG:4326", METRIC_CRS)


def audit_graph(segments: list[NetworkSegment], endpoint_tolerance_m: float = 0.0) -> GraphAudit:
    build = build_graph(segments, endpoint_tolerance_m)
    graph = build.graph
    degree_counts = Counter(dict(graph.degree()).values())
    component_sizes = sorted((len(component) for component in nx.connected_components(graph)), reverse=True)
    endpoint_occurrences = Counter()
    multipart = Counter()
    for segment in segments:
        geometry = segment.geometry_wgs84
        parts = _parts(geometry)
        multipart[len(parts)] += 1
    for edge in build.edges:
        endpoint_occurrences[edge.u] += 1
        endpoint_occurrences[edge.v] += 1
    return GraphAudit(
        endpoint_tolerance_m,
        graph.number_of_nodes(),
        graph.number_of_edges(),
        len(component_sizes),
        component_sizes[0] if component_sizes else 0,
        sum(degree == 0 for _, degree in graph.degree()),
        sum(edge.u == edge.v for edge in build.edges),
        {str(degree): count for degree, count in sorted(degree_counts.items())},
        dict(sorted(multipart.items())),
        dict(sorted(Counter(endpoint_occurrences.values()).items())),
    )


def audit_tolerances(segments: list[NetworkSegment], tolerances_m: Iterable[float] = (0.0, 0.01, 0.1, 1.0)) -> list[GraphAudit]:
    return [audit_graph(segments, tolerance) for tolerance in tolerances_m]


def _edge_lookup(build: GraphBuild) -> dict[str, GraphEdge]:
    return {edge.source_segment_id: edge for edge in build.edges}


def shortest_path_experiment(
    build: GraphBuild,
    origin_node: str,
    destination_node: str,
    disrupted_segment_ids: Iterable[str],
    penalty_factor: float = 100.0,
) -> dict[str, object]:
    """Compare baseline, hard closure, and penalized-edge paths."""
    disrupted = set(disrupted_segment_ids)
    graph = build.graph
    baseline_distance = nx.shortest_path_length(graph, origin_node, destination_node, weight="weight")
    baseline_path = nx.shortest_path(graph, origin_node, destination_node, weight="weight")
    baseline_edges = _path_edges(graph, baseline_path)
    hard = graph.copy()
    hard.remove_edges_from([(u, v, key) for u, v, key, data in hard.edges(keys=True, data=True) if data["source_segment_id"] in disrupted])
    hard_path, hard_distance = _try_shortest(hard, origin_node, destination_node)
    penalized = graph.copy()
    for u, v, key, data in penalized.edges(keys=True, data=True):
        if data["source_segment_id"] in disrupted:
            data["weight"] = data["weight"] * penalty_factor
    penalized_path, penalized_distance = _try_shortest(penalized, origin_node, destination_node)
    return {
        "origin_node": origin_node,
        "destination_node": destination_node,
        "disrupted_segment_ids": sorted(disrupted),
        "baseline_distance_m": float(baseline_distance),
        "baseline_path_edge_count": len(baseline_edges),
        "hard_closure_distance_m": hard_distance,
        "hard_closure_added_distance_m": hard_distance - baseline_distance if hard_distance is not None else None,
        "hard_closure_detour_ratio": hard_distance / baseline_distance if hard_distance is not None and baseline_distance else None,
        "hard_closure_connectivity_lost": hard_distance is None,
        "penalized_distance_m": penalized_distance,
        "penalized_added_distance_m": penalized_distance - baseline_distance if penalized_distance is not None else None,
        "penalized_detour_ratio": penalized_distance / baseline_distance if penalized_distance is not None and baseline_distance else None,
        "penalized_connectivity_lost": penalized_distance is None,
        "removed_edge_count": sum(edge.source_segment_id in disrupted for edge in build.edges),
        "alternative_path_edge_count": len(hard_path) - 1 if hard_path else None,
    }


def _try_shortest(graph: nx.MultiGraph, origin: str, destination: str) -> tuple[list[str] | None, float | None]:
    try:
        path = nx.shortest_path(graph, origin, destination, weight="weight")
        return path, float(nx.shortest_path_length(graph, origin, destination, weight="weight"))
    except nx.NetworkXNoPath:
        return None, None


def _path_edges(graph: nx.MultiGraph, path: list[str]) -> list[tuple[str, str, str]]:
    result: list[tuple[str, str, str]] = []
    for left, right in zip(path, path[1:]):
        candidates = graph.get_edge_data(left, right)
        key = min(candidates, key=lambda item: candidates[item].get("weight", float("inf")))
        result.append((left, right, key))
    return result


def experiment_for_segment(build: GraphBuild, segment_id: str) -> dict[str, object]:
    edge = _edge_lookup(build)[segment_id]
    return shortest_path_experiment(build, edge.u, edge.v, [segment_id])
