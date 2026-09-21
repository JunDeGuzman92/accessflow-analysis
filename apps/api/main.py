"""Thin FastAPI routes over precomputed AccessFlow analytical artifacts."""

from __future__ import annotations

import heapq
import json
import math
import os
import pickle
import asyncio
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from packages.python.accessflow_service import AccessFlowRepository, ArtifactUnavailableError, CsvAccessFlowRepository, DatabaseUnavailableError

try:
    from packages.python.accessflow_service import PostGISAccessFlowRepository
except (ImportError, OSError):
    PostGISAccessFlowRepository = None

from .schemas import (
    AnalyticsSummaryResponse, ErrorResponse, ExplanationCitation, ExplanationResponse,
    GeoJSONGeometry, HealthResponse, MatchResponse, NetworkImpactResponse,
    PredictionRequest, PredictionResponse, Provenance, RestrictionDetailResponse,
    RestrictionPage, RestrictionSummaryResponse, RouteCharacter, RouteComparison,
    RoutePath, RouteResponse, SpatialFeatureResponse, SpatialResponse, WalkEvent,
    normalize_geometry,
)


VERSION = "0.1.0"

ROUTE_LIMITATIONS = (
    "CANDIDATE_SEGMENTS_ARE_NOT_CONFIRMED_CLOSURES",
    "EDGE_LENGTHS_USE_HAVERSINE_WGS84_APPROXIMATION",
    "PEDESTRIAN_NETWORK_TOPOLOGY_IS_GEOMETRY_DERIVED",
)

_ROUTING_INDEX: dict | None = None


def _load_routing_index() -> dict:
    """Lazily load the precomputed pedestrian routing graph (dependency-free pickle)."""
    global _ROUTING_INDEX
    if _ROUTING_INDEX is not None:
        return _ROUTING_INDEX
    data_dir = Path(os.environ.get("ACCESSFLOW_ANALYTICS_DIR", "data/processed"))
    graph_path = data_dir / "routing-graph.pkl"
    if not graph_path.exists():
        raise ArtifactUnavailableError("Routing graph artifact is unavailable; run scripts/build_routing_graph.py first")
    with graph_path.open("rb") as handle:
        data = pickle.load(handle)
    if data.get("schema") != "routing-graph-v1":
        raise ArtifactUnavailableError("Routing graph artifact has an unsupported schema")
    nodes: dict[int, list[float]] = {int(k): v for k, v in data["nodes"].items()}
    edges = data["edges"]
    adjacency: dict[int, list[tuple[int, float, int]]] = {}
    components: dict[int, int] = {}
    for index, edge in enumerate(edges):
        u, v = edge["u"], edge["v"]
        adjacency.setdefault(u, []).append((v, edge["len_m"], index))
        adjacency.setdefault(v, []).append((u, edge["len_m"], index))

    def label_component(start: int, label: int) -> None:
        stack = [start]
        while stack:
            current = stack.pop()
            if current in components:
                continue
            components[current] = label
            for neighbor, _, _ in adjacency.get(current, []):
                if neighbor not in components:
                    stack.append(neighbor)

    label = 0
    for edge in edges:
        for node in (edge["u"], edge["v"]):
            if node not in components:
                label_component(node, label)
                label += 1

    barriers: dict[str, frozenset[str]] = {
        restriction_id: frozenset(feature_ids)
        for restriction_id, feature_ids in data.get("barriers", {}).items()
    }
    all_barrier_segments = frozenset().union(*barriers.values()) if barriers else frozenset()

    _ROUTING_INDEX = {
        "nodes": nodes,
        "edges": edges,
        "adjacency": adjacency,
        "components": components,
        "barriers": barriers,
        "all_barrier_segments": all_barrier_segments,
    }
    return _ROUTING_INDEX


def _snap_node(index: dict, point: tuple[float, float]) -> int:
    nodes = index["nodes"]
    best_node = None
    best_distance = float("inf")
    for node_id, (lng, lat) in nodes.items():
        distance = (lng - point[0]) ** 2 + (lat - point[1]) ** 2
        if distance < best_distance:
            best_distance = distance
            best_node = node_id
    if best_node is None:
        raise ArtifactUnavailableError("Routing graph is empty")
    return best_node


def _dijkstra(index: dict, origin: int, destination: int, forbidden_segments: frozenset[str]) -> list[tuple[int, int, float]] | None:
    """Return the shortest path as a list of (node, edge_index, length) or None when unreachable."""
    adjacency = index["adjacency"]
    edges = index["edges"]
    distances: dict[int, float] = {origin: 0.0}
    previous: dict[int, tuple[int, int, float]] = {}
    heap: list[tuple[float, int]] = [(0.0, origin)]
    visited: set[int] = set()

    while heap:
        current_distance, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        if node == destination:
            break
        for neighbor, length_m, edge_index in adjacency.get(node, []):
            if neighbor in visited:
                continue
            if forbidden_segments and edges[edge_index]["seg"] in forbidden_segments:
                continue
            candidate = current_distance + length_m
            if candidate < distances.get(neighbor, float("inf")):
                distances[neighbor] = candidate
                previous[neighbor] = (node, edge_index, length_m)
                heapq.heappush(heap, (candidate, neighbor))

    if destination not in distances:
        return None

    path: list[tuple[int, int, float]] = []
    cursor = destination
    while cursor != origin:
        step = previous.get(cursor)
        if step is None:
            return None
        path.append((cursor, step[1], step[2]))
        cursor = step[0]
    path.reverse()
    return path


def _path_geometry(index: dict, origin_node: int, path: list[tuple[int, int, float]] | None) -> GeoJSONGeometry | None:
    """Stitch edge geometries along the path, orienting each edge by node identity.

    Orientation is decided from the path's node chain (exact) rather than by
    comparing coordinates, because the graph builder clusters endpoints within
    1e-6 degrees while individual edge vertices keep their original values;
    coordinate matching misoriented edges and corrupted drawn routes.
    """
    if not path:
        return None
    edges = index["edges"]
    nodes = index["nodes"]

    def same_point(a: list[float], b: list[float]) -> bool:
        return abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9

    coordinates: list[list[float]] = [list(nodes[origin_node])]
    for step_index, (_node, edge_index, _length) in enumerate(path):
        edge = edges[edge_index]
        edge_coords = edge["coords"]
        from_node = origin_node if step_index == 0 else path[step_index - 1][0]
        to_node = _node
        if edge["u"] == from_node and edge["v"] == to_node:
            ordered = edge_coords
        elif edge["v"] == from_node and edge["u"] == to_node:
            ordered = [list(pt) for pt in reversed(edge_coords)]
        elif same_point(list(edge_coords[0]), coordinates[-1]):
            ordered = edge_coords
        else:
            ordered = [list(pt) for pt in reversed(edge_coords)]
        if ordered and same_point(list(ordered[0]), coordinates[-1]):
            coordinates.extend([list(pt) for pt in ordered[1:]])
        else:
            coordinates.extend([list(pt) for pt in ordered])
    return GeoJSONGeometry(type="LineString", coordinates=coordinates)


def _barriers_on_path(index: dict, path: list[tuple[int, int, float]] | None, forbidden: frozenset[str]) -> int:
    if not path:
        return 0
    edges = index["edges"]
    return sum(1 for _node, edge_index, _length in path if edges[edge_index]["seg"] in forbidden)


class _RateLimiter:
    """In-process token bucket per client; pure stdlib, no external service required."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = max(0, limit)
        self.window = max(0.001, window_seconds)
        self._counts: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str, now: float) -> tuple[bool, float]:
        if self.limit == 0:
            return True, 0.0
        timestamps = self._counts[key]
        cutoff = now - self.window
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)
        if len(timestamps) >= self.limit:
            retry_after = max(0.0, timestamps[0] + self.window - now)
            return False, retry_after
        timestamps.append(now)
        if not timestamps:
            timestamps.append(now)
        return True, 0.0


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _parse_coordinate_pair(value: str, label: str) -> tuple[float, float]:
    parts = value.split(",")
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail={"code": "INVALID_COORDINATES", "message": f"{label} must be 'longitude,latitude'"})
    try:
        lon, lat = float(parts[0].strip()), float(parts[1].strip())
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": "INVALID_COORDINATES", "message": f"{label} must be numeric 'longitude,latitude'"})
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise HTTPException(status_code=400, detail={"code": "INVALID_COORDINATES", "message": f"{label} is outside WGS84 bounds"})
    return lon, lat


def _route_character(index: dict, path: list[tuple[int, int, float]] | None) -> RouteCharacter | None:
    """Aggregate real sidewalk/road attributes of the path edges from the source network."""
    if not path:
        return None
    edges = index["edges"]
    if "character" not in edges[path[0][1]]:
        return None
    sidewalk_counts: dict[str, int] = {}
    road_type_counts: dict[str, int] = {}
    crosswalk_count = 0
    signal_count = 0
    for _node, edge_index, _length in path:
        character = edges[edge_index].get("character")
        if not character:
            continue
        sidewalk = character.get("sidewalk")
        if sidewalk:
            sidewalk_counts[sidewalk] = sidewalk_counts.get(sidewalk, 0) + 1
        road_type = character.get("road_type")
        if road_type:
            road_type_counts[road_type] = road_type_counts.get(road_type, 0) + 1
        if character.get("crosswalk"):
            crosswalk_count += 1
        if character.get("px_type"):
            signal_count += 1
    if not (sidewalk_counts or road_type_counts or crosswalk_count or signal_count):
        return None
    return RouteCharacter(
        sidewalk_counts=sidewalk_counts,
        road_type_counts=road_type_counts,
        crosswalk_count=crosswalk_count,
        pedestrian_signal_count=signal_count,
    )


def _walk_events(index: dict, path: list[tuple[int, int, float]] | None) -> list[WalkEvent]:
    """Emit real route features (sidewalk coverage, crosswalks, signals) at distances along the path."""
    events: list[WalkEvent] = []
    if not path:
        return events
    edges = index["edges"]
    distance = 0.0
    previous_sidewalk: str | None = None
    for _node, edge_index, length in path:
        character = edges[edge_index].get("character") or {}
        sidewalk = character.get("sidewalk")
        if sidewalk and sidewalk != previous_sidewalk:
            events.append(WalkEvent(at_m=round(distance, 1), kind="sidewalk_change", label=sidewalk))
            previous_sidewalk = sidewalk
        if character.get("crosswalk"):
            events.append(WalkEvent(at_m=round(distance, 1), kind="crosswalk", label="Crosswalk"))
        if character.get("px_type"):
            events.append(WalkEvent(at_m=round(distance, 1), kind="signal", label=f"Pedestrian signal ({character['px_type']})"))
        distance += length
    return events


def _compute_route(origin: str, destination: str, avoid: str | None) -> RouteResponse:
    index = _load_routing_index()

    origin_point = _parse_coordinate_pair(origin, "origin")
    destination_point = _parse_coordinate_pair(destination, "destination")

    if avoid == "all":
        forbidden = index["all_barrier_segments"]
    elif avoid:
        restriction_barriers = index["barriers"].get(avoid)
        if restriction_barriers is None:
            raise HTTPException(status_code=404, detail={"code": "RESTRICTION_NOT_FOUND", "message": "Restriction has no candidate segment evidence in the available analytical artifacts."})
        forbidden = restriction_barriers
    else:
        forbidden = frozenset()

    origin_node = _snap_node(index, origin_point)
    destination_node = _snap_node(index, destination_point)
    components = index["components"]
    if components.get(origin_node) != components.get(destination_node):
        return RouteResponse(
            origin=list(origin_point), destination=list(destination_point),
            origin_node=origin_node, destination_node=destination_node,
            avoid=avoid, baseline=RoutePath(geometry=None, distance_m=0.0, edge_count=0, barriers_on_path=0),
            recommended=None, comparison=None, reachable=False,
            limitations=list(ROUTE_LIMITATIONS), provenance=_provenance(),
        )

    baseline = _dijkstra(index, origin_node, destination_node, frozenset())
    baseline_barriers = _barriers_on_path(index, baseline, index["all_barrier_segments"]) if baseline else 0
    baseline_path = RoutePath(
        geometry=_path_geometry(index, origin_node, baseline),
        distance_m=round(sum(edge[2] for edge in baseline), 1) if baseline else 0.0,
        edge_count=len(baseline),
        barriers_on_path=baseline_barriers,
        walk_events=_walk_events(index, baseline),
    )

    if not forbidden:
        return RouteResponse(
            origin=list(origin_point), destination=list(destination_point),
            origin_node=origin_node, destination_node=destination_node,
            avoid=avoid, baseline=baseline_path, recommended=None, comparison=None,
            route_character=_route_character(index, baseline),
            reachable=True, limitations=list(ROUTE_LIMITATIONS), provenance=_provenance(),
        )

    recommended = _dijkstra(index, origin_node, destination_node, forbidden)
    recommended_barriers = _barriers_on_path(index, recommended, forbidden) if recommended else 0
    recommended_path = (
        RoutePath(
            geometry=_path_geometry(index, origin_node, recommended),
            distance_m=round(sum(edge[2] for edge in recommended), 1),
            edge_count=len(recommended),
            barriers_on_path=recommended_barriers,
            walk_events=_walk_events(index, recommended),
        )
        if recommended is not None
        else None
    )

    comparison = None
    if recommended is not None and baseline:
        avoided_on_baseline = sum(1 for edge in baseline if index["edges"][edge[1]]["seg"] in forbidden)
        comparison = RouteComparison(
            added_distance_m=round(recommended_path.distance_m - baseline_path.distance_m, 1),
            distance_ratio=round(recommended_path.distance_m / baseline_path.distance_m, 3) if baseline_path.distance_m > 0 else None,
            avoided_barrier_count=avoided_on_baseline,
        )

    return RouteResponse(
        origin=list(origin_point), destination=list(destination_point),
        origin_node=origin_node, destination_node=destination_node,
        avoid=avoid, baseline=baseline_path, recommended=recommended_path,
        comparison=comparison, reachable=True,
        route_character=_route_character(index, recommended if recommended is not None else baseline),
        limitations=list(ROUTE_LIMITATIONS), provenance=_provenance(),
    )


SEVERITY_INTERPRETATIONS = {
    "SEVERE": "Removing the candidate segments disconnects part of the pedestrian network — there may be no reasonable walking detour. People who rely on this corridor should plan alternate routes well in advance.",
    "HIGH": "The modeled detour is substantial. Pedestrians with limited mobility or assistive devices may find the alternative route difficult or impractical.",
    "MODERATE": "A reasonable detour exists; the extra travel distance is noticeable but manageable for most pedestrians.",
    "LOW": "Little to no network-level impact is modeled for this restriction.",
    "NOT_EVALUATED": "The current analytical artifacts do not contain enough evidence to evaluate this restriction's network impact.",
}

EXPLANATION_LIMITATIONS = (
    "EXPLANATION_IS_GENERATED_FROM_PRECOMPUTED_ARTIFACTS",
    "CANDIDATE_SEGMENTS_ARE_NOT_CONFIRMED_CLOSURES",
)

LLM_SYSTEM_PROMPT = (
    "You are an accessibility analyst for AccessFlow Toronto. Rewrite the provided explanation "
    "more clearly and concisely for a resident or city operations user. Use ONLY the facts given; "
    "never invent streets, buildings, disruptions, accessibility infrastructure, barriers, routes, "
    "distances, or geographic conditions. If information is missing, say so plainly. Keep all numbers "
    "exactly as provided."
)


def _llm_enhance(kind: str, headline: str, narrative: str, bullets: list[str]) -> str | None:
    """Optionally rephrase an explanation with a configured OpenAI-compatible LLM. Returns None when unconfigured or on any failure."""
    base_url = os.environ.get("ACCESSFLOW_LLM_BASE_URL")
    api_key = os.environ.get("ACCESSFLOW_LLM_API_KEY")
    if not base_url or not api_key:
        return None
    model = os.environ.get("ACCESSFLOW_LLM_MODEL", "gpt-4o-mini")
    facts = "\n".join([f"Headline: {headline}", f"Narrative: {narrative}", "Bullets:\n- " + "\n- ".join(bullets)])
    try:
        import httpx
        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": LLM_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Explanation kind: {kind}\n\n{facts}"},
                ],
                "max_tokens": 400,
                "temperature": 0.2,
            },
            timeout=8.0,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        text = content.strip() if isinstance(content, str) else ""
        return text or None
    except Exception:
        return None


def _format_duration(hours: float | None) -> str:
    if hours is None:
        return "unknown duration"
    if hours >= 24:
        return f"about {round(hours / 24)} days ({round(hours)} hours)"
    return f"about {round(hours)} hours"


def _explain_restriction(repository: AccessFlowRepository, restriction_id: str) -> ExplanationResponse:
    detail = repository.get_restriction(restriction_id)
    if detail is None:
        raise HTTPException(status_code=404, detail={"code": "RESTRICTION_NOT_FOUND", "message": "Restriction is not represented in the available analytical artifacts."})
    impacts = repository.get_network_impact(restriction_id) or []
    matches = repository.get_matches(restriction_id) or []

    direct = sum(1 for m in matches if m.match_type == "direct_intersection")
    proximity = sum(1 for m in matches if m.match_type == "proximity")
    fallback = sum(1 for m in matches if m.match_type == "point_fallback")

    impact = impacts[0] if impacts else None
    severity = detail.impact_severity
    interpretation = SEVERITY_INTERPRETATIONS.get(severity, SEVERITY_INTERPRETATIONS["NOT_EVALUATED"])

    match_phrases = []
    if direct:
        match_phrases.append(f"{direct} by direct intersection")
    if proximity:
        match_phrases.append(f"{proximity} by proximity")
    if fallback:
        match_phrases.append(f"{fallback} by nearest-point fallback")
    match_sentence = (
        "Its location matched " + str(detail.candidate_edge_count) + " candidate pedestrian-network segment(s)"
        + (" — " + " and ".join(match_phrases) + " — " if match_phrases else " — ")
        + f"giving an evidence confidence of {detail.evidence_confidence}."
        if detail.candidate_edge_count
        else "No candidate pedestrian-network segments were matched for this location, so evidence confidence is INSUFFICIENT."
    )

    impact_sentences = []
    if impact is not None and impact.evaluation_status == "EVALUATED":
        if impact.alternative_path_edge_count > 0:
            added = impact.median_added_replacement_distance_m
            ratio = impact.median_replacement_ratio
            impact_sentences.append(
                f"Replacement-path analysis found alternative routes around the affected segments; the median detour adds "
                f"{round(added) if added is not None else 'an unreported'} meters"
                + (f" ({round(ratio, 1)}x the original path)" if ratio is not None else "") + "."
            )
        else:
            impact_sentences.append("Replacement-path analysis did not identify an alternative route around the affected segments.")
        if impact.local_connectivity_loss_count > 0:
            impact_sentences.append(f"Removing the candidate segments disconnects the network in {impact.local_connectivity_loss_count} place(s).")
        else:
            impact_sentences.append("Removing the candidate segments does not disconnect the local network.")
    elif impact is not None:
        impact_sentences.append(f"Replacement-path evaluation is {impact.evaluation_status} for this restriction.")

    headline = f"{severity.replace('_', ' ').title()} impact — {detail.candidate_edge_count} candidate segment(s), {detail.evidence_confidence} confidence"
    narrative = (
        f"Restriction {detail.restriction_id} is {detail.evaluation_status.replace('_', ' ').lower()} in the current evidence. "
        f"{match_sentence} "
        + " ".join(impact_sentences)
        + f" The impact severity is assessed as {severity}. "
        + f"This restriction is in effect for {_format_duration(detail.duration_hours)}. "
        + f"Interpretation: {interpretation}"
    )

    bullets = [
        f"{detail.candidate_edge_count} candidate segments (spatial evidence only, not confirmed closures)",
        f"Evidence confidence: {detail.evidence_confidence}",
        f"Impact severity: {severity}",
    ]
    if impact is not None and impact.median_added_replacement_distance_m is not None:
        bullets.append(f"Median detour: +{round(impact.median_added_replacement_distance_m)} m ({round(impact.median_replacement_ratio, 1) if impact.median_replacement_ratio is not None else '—'}x)")
    if impact is not None:
        bullets.append(f"Connectivity loss: {'yes' if impact.local_connectivity_loss_count > 0 else 'no'}")
    bullets.append(f"Duration: {_format_duration(detail.duration_hours)}")

    return ExplanationResponse(
        kind="restriction",
        headline=headline,
        narrative=narrative,
        bullets=bullets,
        citations=[ExplanationCitation(restriction_id=detail.restriction_id, fields=[
            "evaluation_status", "impact_severity", "evidence_confidence", "candidate_edge_count",
            "duration_hours", "network_impact.median_added_replacement_distance_m",
            "network_impact.local_connectivity_loss_count",
        ])],
        method="deterministic-rules-v1",
        limitations=list(EXPLANATION_LIMITATIONS) + list(detail.limitations),
        provenance=_provenance(detail.source_snapshot),
    )


def _explain_route(origin: str, destination: str, avoid: str | None) -> ExplanationResponse:
    route = _compute_route(origin, destination, avoid)

    if not route.reachable:
        return ExplanationResponse(
            kind="route",
            headline="No walking route exists between these points",
            narrative="Origin and destination snap to disconnected parts of the Toronto pedestrian network in the current data. No walking route can be computed between them; this reflects gaps in the published network, not a closure.",
            bullets=[],
            citations=[],
            method="deterministic-rules-v1",
            limitations=list(EXPLANATION_LIMITATIONS) + list(route.limitations),
            provenance=_provenance(),
        )

    avoid_label = "all represented disruptions" if route.avoid == "all" else f"restriction {route.avoid}"
    baseline = route.baseline

    if route.avoid and route.recommended is not None and route.comparison is not None:
        added = route.comparison.added_distance_m
        ratio = route.comparison.distance_ratio
        avoided = route.comparison.avoided_barrier_count
        if added and added > 0:
            headline = f"Recommended route avoids {avoided} barrier segment(s) for +{round(added)} m"
            detail_sentence = (
                f"Avoiding the candidate segments tied to {avoid_label} adds {round(added)} meters "
                f"({ratio}x the baseline) and removes {avoided} barrier segment(s) from the path."
            )
        else:
            headline = f"Recommended route avoids {avoided} barrier segment(s) at no extra distance"
            detail_sentence = (
                f"Avoiding the candidate segments tied to {avoid_label} costs no additional distance — "
                f"the recommended path is as short as the baseline."
            )
    elif route.avoid and route.recommended is None:
        headline = "No alternative path after avoidance"
        detail_sentence = (
            f"No walking path exists between these points once the candidate segments tied to {avoid_label} are removed. "
            "The affected area may fragment the pedestrian network."
        )
    elif baseline.barriers_on_path > 0:
        headline = f"Shortest route crosses {baseline.barriers_on_path} barrier segment(s)"
        detail_sentence = (
            f"The shortest path crosses {baseline.barriers_on_path} candidate segment(s) associated with disruption evidence. "
            "Request the route again with avoidance to see the alternative."
        )
    else:
        headline = "Shortest route is clear of represented disruptions"
        detail_sentence = "The shortest path does not cross any candidate barrier segment in the current evidence."

    narrative = (
        f"The shortest walking route between your points is {round(baseline.distance_m)} meters across "
        f"{baseline.edge_count} pedestrian-network segments. {detail_sentence} "
        "Candidate segments are spatial evidence, not confirmed closures."
    )

    bullets = [f"Baseline: {round(baseline.distance_m)} m, {baseline.edge_count} segments"]
    if route.recommended is not None:
        bullets.append(f"Recommended: {round(route.recommended.distance_m)} m, {route.recommended.edge_count} segments")
    if route.comparison is not None:
        bullets.append(f"Avoided barrier segments on baseline: {route.comparison.avoided_barrier_count}")
        if route.comparison.added_distance_m is not None:
            bullets.append(f"Detour cost: +{round(route.comparison.added_distance_m)} m")

    return ExplanationResponse(
        kind="route",
        headline=headline,
        narrative=narrative,
        bullets=bullets,
        citations=[],
        method="deterministic-rules-v1",
        limitations=list(EXPLANATION_LIMITATIONS) + list(route.limitations),
        provenance=_provenance(),
    )


def _explain_overview(repository: AccessFlowRepository) -> ExplanationResponse:
    summary = repository.analytics_summary()
    items, total = repository.list_restrictions(offset=0, limit=100, evaluation_status=None, impact_severity=None, evidence_confidence=None)
    total_represented = summary["total_restrictions_represented"]
    evaluated = summary["evaluated_restrictions"]
    not_evaluated = total_represented - evaluated
    severity_distribution = summary["impact_severity_distribution"]
    confidence_distribution = summary["evidence_confidence_distribution"]

    durations = [item.duration_hours for item in items if item.duration_hours is not None]
    duration_sentence = ""
    if durations:
        durations_sorted = sorted(durations)
        median = durations_sorted[len(durations_sorted) // 2]
        duration_sentence = f" Of the {len(durations)} with duration data, the median closure lasts {_format_duration(median)}."

    severity_phrases = ", ".join(f"{count} {severity}" for severity, count in sorted(severity_distribution.items(), key=lambda pair: -pair[1]))
    confidence_phrases = ", ".join(f"{count} {confidence}" for confidence, count in sorted(confidence_distribution.items(), key=lambda pair: -pair[1]))

    headline = f"{total_represented} street disruptions represented in current evidence"
    narrative = (
        f"The current analytical artifacts represent {total_represented} restrictions from the Toronto Open Data "
        f"road-restrictions feed. {evaluated} have network-level evaluation; {not_evaluated} are not evaluated. "
        f"Impact severity: {severity_phrases}. Evidence confidence: {confidence_phrases}.{duration_sentence} "
        "Every record is research-oriented candidate evidence — segments are not confirmed closures."
    )

    return ExplanationResponse(
        kind="overview",
        headline=headline,
        narrative=narrative,
        bullets=[
            f"{evaluated} evaluated / {not_evaluated} not evaluated",
            f"Severity: {severity_phrases}",
            f"Confidence: {confidence_phrases}",
        ],
        citations=[ExplanationCitation(restriction_id=None, fields=[
            "analytics_summary.total_restrictions_represented",
            "analytics_summary.evaluated_restrictions",
            "analytics_summary.impact_severity_distribution",
            "analytics_summary.evidence_confidence_distribution",
        ])],
        method="deterministic-rules-v1",
        limitations=list(EXPLANATION_LIMITATIONS),
        provenance=_provenance(),
    )


def _provenance(snapshot: str | None = None) -> Provenance:
    return Provenance(source_snapshot=snapshot)


def _repository_from_environment() -> AccessFlowRepository:
    backend = os.environ.get("ACCESSFLOW_REPOSITORY_BACKEND", "artifact").lower()
    data_dir = Path(os.environ.get("ACCESSFLOW_ANALYTICS_DIR", "data/processed"))
    if backend == "postgis":
        if PostGISAccessFlowRepository is None:
            raise ArtifactUnavailableError("PostGIS repository not available (pyproj DLL blocked)")
        return PostGISAccessFlowRepository.from_environment(data_dir=data_dir)
    return CsvAccessFlowRepository(data_dir)


def create_app(repository: AccessFlowRepository | None = None) -> FastAPI:
    app = FastAPI(title="AccessFlow Toronto API", version=VERSION, description="Research-oriented candidate disruption evidence. Candidate segments are not confirmed closures.")

    origins = [origin.strip() for origin in os.environ.get("ACCESSFLOW_CORS_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",") if origin.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    api_token = os.environ.get("ACCESSFLOW_API_TOKEN", "").strip()
    rate_limit_requests = int(os.environ.get("ACCESSFLOW_RATE_LIMIT_REQUESTS", "240"))
    rate_limit_window = float(os.environ.get("ACCESSFLOW_RATE_LIMIT_WINDOW", "60"))
    rate_limiter = _RateLimiter(rate_limit_requests, rate_limit_window)

    @app.middleware("http")
    async def hardening_middleware(request: Request, call_next):
        path = request.url.path

        if path.startswith("/api/v1"):
            if api_token:
                authorization = request.headers.get("authorization", "")
                scheme, _, credential = authorization.partition(" ")
                if scheme.lower() != "bearer" or not credential or not secrets.compare_digest(credential.strip(), api_token):
                    return JSONResponse(status_code=401, content={"detail": {"code": "UNAUTHORIZED", "message": "A valid bearer token is required."}}, headers={"WWW-Authenticate": "Bearer"})

            allowed, retry_after = rate_limiter.allow(_client_key(request), time.monotonic())
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": {"code": "RATE_LIMITED", "message": "Too many requests; slow down."}},
                    headers={"Retry-After": str(max(1, round(retry_after)))},
                )

        response = await call_next(request)

        if request.method == "GET" and path.startswith("/api/v1"):
            response.headers.setdefault("Cache-Control", "public, max-age=60")

        return response

    app.state.repository = repository

    @app.exception_handler(ArtifactUnavailableError)
    async def unavailable_artifact(_request: Request, exc: ArtifactUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": {"code": "ANALYTICAL_ARTIFACT_UNAVAILABLE", "message": str(exc)}})

    @app.exception_handler(DatabaseUnavailableError)
    async def unavailable_database(_request: Request, exc: DatabaseUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": {"code": "PERSISTENCE_UNAVAILABLE", "message": str(exc)}})

    def get_repository() -> AccessFlowRepository:
        if app.state.repository is None:
            try:
                app.state.repository = _repository_from_environment()
            except ArtifactUnavailableError as exc:
                raise HTTPException(status_code=503, detail={"code": "ANALYTICAL_ARTIFACT_UNAVAILABLE", "message": str(exc)}) from exc
            except DatabaseUnavailableError as exc:
                raise HTTPException(status_code=503, detail={"code": "PERSISTENCE_UNAVAILABLE", "message": str(exc)}) from exc
        return app.state.repository

    class ConnectionManager:
        def __init__(self):
            self.active_connections: list[WebSocket] = []

        async def connect(self, websocket: WebSocket):
            await websocket.accept()
            self.active_connections.append(websocket)

        def disconnect(self, websocket: WebSocket):
            self.active_connections.remove(websocket)

        async def broadcast(self, message: dict):
            for connection in self.active_connections[:]:
                try:
                    await connection.send_json(message)
                except Exception:
                    self.active_connections.remove(connection)

    ws_manager = ConnectionManager()

    @app.get("/health", response_model=HealthResponse, summary="Service health")
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=VERSION)

    def _massing_dir() -> Path:
        return Path(os.environ.get("ACCESSFLOW_ANALYTICS_DIR", "data/processed")) / "massing"

    @app.get("/api/v1/massing/manifest", summary="3D Massing grid manifest")
    def massing_manifest() -> JSONResponse:
        path = _massing_dir() / "manifest.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail={"code": "MASSING_UNAVAILABLE", "message": "3D Massing artifact not built; run scripts/build_massing_geojson.py first"})
        return JSONResponse(json.loads(path.read_text(encoding="utf-8")))

    @app.get("/api/v1/massing/{cell}", summary="One 3D Massing grid cell")
    def massing_cell(cell: str) -> JSONResponse:
        if not re.fullmatch(r"cell_\d+_\d+", cell):
            raise HTTPException(status_code=400, detail={"code": "INVALID_CELL", "message": "Cell names must look like cell_1_2"})
        manifest_path = _massing_dir() / "manifest.json"
        if not manifest_path.exists():
            raise HTTPException(status_code=404, detail={"code": "MASSING_UNAVAILABLE", "message": "3D Massing artifact not built; run scripts/build_massing_geojson.py first"})
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if cell not in manifest.get("cells", {}):
            raise HTTPException(status_code=404, detail={"code": "CELL_NOT_FOUND", "message": "Cell is outside the available 3D Massing clip area"})
        cell_path = _massing_dir() / f"{cell}.json"
        if not cell_path.exists():
            raise HTTPException(status_code=404, detail={"code": "CELL_NOT_FOUND", "message": "Cell file is missing from the artifact"})
        return JSONResponse(json.loads(cell_path.read_text(encoding="utf-8")))

    @app.get("/api/v1/pois", summary="Walk-service POI layers (benches, washrooms, cooling, libraries, community centres, transit stops)")
    def poi_layers() -> JSONResponse:
        path = Path(os.environ.get("ACCESSFLOW_ANALYTICS_DIR", "data/processed")) / "poi-layers.geojson"
        if not path.exists():
            raise HTTPException(status_code=404, detail={"code": "POI_LAYERS_UNAVAILABLE", "message": "POI layers artifact not built; run scripts/build_poi_layers.py first"})
        return JSONResponse(json.loads(path.read_text(encoding="utf-8")))

    @app.get("/api/v1/pois/provenance", summary="POI layers dataset provenance")
    def poi_provenance() -> JSONResponse:
        path = Path(os.environ.get("ACCESSFLOW_ANALYTICS_DIR", "data/processed")) / "poi-layers-provenance.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail={"code": "POI_LAYERS_UNAVAILABLE", "message": "POI layers artifact not built; run scripts/build_poi_layers.py first"})
        return JSONResponse(json.loads(path.read_text(encoding="utf-8")))

    @app.get("/api/v1/restrictions", response_model=RestrictionPage, responses={503: {"model": ErrorResponse}}, summary="List represented restrictions")
    def list_restrictions(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), evaluation_status: str | None = None, impact_severity: str | None = None, evidence_confidence: str | None = None, repository: AccessFlowRepository = Depends(get_repository)) -> RestrictionPage:
        items, total = repository.list_restrictions(offset=offset, limit=limit, evaluation_status=evaluation_status, impact_severity=impact_severity, evidence_confidence=evidence_confidence)
        coords = getattr(repository, '_coordinates', {})
        locations = getattr(repository, '_locations', {})
        return RestrictionPage(items=[RestrictionSummaryResponse(**item.__dict__, provenance=_provenance(item.source_snapshot), coordinates=coords.get(item.restriction_id), location=locations.get(item.restriction_id)) for item in items], total=total, offset=offset, limit=limit)

    @app.get("/api/v1/restrictions/{restriction_id}", response_model=RestrictionDetailResponse, responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}, summary="Get one represented restriction")
    def restriction_detail(restriction_id: str, repository: AccessFlowRepository = Depends(get_repository)) -> RestrictionDetailResponse:
        item = repository.get_restriction(restriction_id)
        if item is None:
            raise HTTPException(status_code=404, detail={"code": "RESTRICTION_NOT_FOUND", "message": "Restriction is not represented in the available analytical artifacts."})
        coords = getattr(repository, '_coordinates', {})
        locations = getattr(repository, '_locations', {})
        return RestrictionDetailResponse(
            restriction_id=item.restriction_id, evaluation_status=item.evaluation_status,
            impact_severity=item.impact_severity, evidence_confidence=item.evidence_confidence,
            candidate_edge_count=item.candidate_edge_count, impact_evaluable=item.impact_evaluable,
            valid_restriction_polyline=item.valid_restriction_polyline,
            fallback_geometry_used=item.fallback_geometry_used, duration_hours=item.duration_hours,
            reason_codes=list(item.reason_codes), limitations=list(item.limitations),
            restriction_geometry=item.restriction_geometry, provenance=_provenance(item.source_snapshot),
            coordinates=coords.get(item.restriction_id), match_type=item.match_type,
            location=locations.get(item.restriction_id),
        )

    @app.get("/api/v1/restrictions/{restriction_id}/matches", response_model=list[MatchResponse], responses={404: {"model": ErrorResponse}}, summary="List evaluated candidate matches")
    def matches(restriction_id: str, repository: AccessFlowRepository = Depends(get_repository)) -> list[MatchResponse]:
        items = repository.get_matches(restriction_id)
        if items is None:
            raise HTTPException(status_code=404, detail={"code": "RESTRICTION_NOT_FOUND", "message": "Restriction is not represented in the available analytical artifacts."})
        return [MatchResponse(**item.__dict__) for item in items]

    @app.get("/api/v1/restrictions/{restriction_id}/spatial", response_model=SpatialResponse, responses={404: {"model": ErrorResponse}}, summary="Get authoritative spatial evidence")
    def spatial(restriction_id: str, repository: AccessFlowRepository = Depends(get_repository)) -> SpatialResponse:
        restriction = repository.get_restriction(restriction_id)
        matches = repository.get_matches(restriction_id)
        if restriction is None or matches is None:
            raise HTTPException(status_code=404, detail={"code": "RESTRICTION_NOT_FOUND", "message": "Restriction is not represented in the available analytical artifacts."})

        restriction_geometry = normalize_geometry(restriction.restriction_geometry)
        features: list[SpatialFeatureResponse] = []
        for rank, item in enumerate(matches, start=1):
            geometry = normalize_geometry(item.geometry)
            features.append(SpatialFeatureResponse(
                feature_id=item.pedestrian_feature_id,
                geometry=GeoJSONGeometry(**geometry) if geometry is not None else None,
                match_type=item.match_type,
                confidence=item.evidence_confidence,
                distance_m=item.distance_m,
                source=item.source,
                candidate_rank=item.candidate_rank or rank,
                candidate_status=item.candidate_status,
            ))

        geometry_values = [restriction_geometry] + [feature.geometry for feature in features]
        available_count = sum(value is not None for value in geometry_values)
        if available_count == 0:
            geometry_status = "NOT_AVAILABLE"
        elif available_count == len(geometry_values):
            geometry_status = "AVAILABLE"
        else:
            geometry_status = "PARTIAL"
        matched_features = [feature for feature in features if feature.geometry is not None]
        provenance = _provenance(restriction.source_snapshot)
        return SpatialResponse(
            restriction_id=restriction_id,
            restriction_geometry=GeoJSONGeometry(**restriction_geometry) if restriction_geometry is not None else None,
            matched_features=matched_features,
            candidate_features=features,
            crs="EPSG:4326",
            evidence_confidence=restriction.evidence_confidence,
            geometry_status=geometry_status,
            provenance=provenance,
        )

    @app.get("/api/v1/restrictions/{restriction_id}/network-impact", response_model=list[NetworkImpactResponse], responses={404: {"model": ErrorResponse}}, summary="Get precomputed replacement-path evidence")
    def network_impact(restriction_id: str, repository: AccessFlowRepository = Depends(get_repository)) -> list[NetworkImpactResponse]:
        items = repository.get_network_impact(restriction_id)
        if items is None:
            raise HTTPException(status_code=404, detail={"code": "RESTRICTION_NOT_FOUND", "message": "Restriction is not represented in the available analytical artifacts."})
        return [NetworkImpactResponse(
            scenario=item.scenario, evaluation_status=item.evaluation_status,
            candidate_edge_count=item.candidate_edge_count, evaluated_edge_count=item.evaluated_edge_count,
            alternative_path_edge_count=item.alternative_path_edge_count,
            local_connectivity_loss_count=item.local_connectivity_loss_count,
            local_connectivity_loss_fraction=item.local_connectivity_loss_fraction,
            median_replacement_ratio=item.median_replacement_ratio,
            max_replacement_ratio=item.max_replacement_ratio,
            median_added_replacement_distance_m=item.median_added_replacement_distance_m,
            max_added_replacement_distance_m=item.max_added_replacement_distance_m,
            set_evaluation_status=item.set_evaluation_status,
            set_component_increase=item.set_component_increase,
            set_disconnected_boundary_pair_count=item.set_disconnected_boundary_pair_count,
            limitations=list(item.limitations), provenance=_provenance(),
        ) for item in items]

    @app.get("/api/v1/analytics/summary", response_model=AnalyticsSummaryResponse, responses={503: {"model": ErrorResponse}}, summary="Summarize represented analytical records")
    def summary(repository: AccessFlowRepository = Depends(get_repository)) -> AnalyticsSummaryResponse:
        return AnalyticsSummaryResponse(**repository.analytics_summary(), provenance=_provenance())

    @app.post("/api/v1/predict", response_model=PredictionResponse, summary="Predict accessibility impact")
    async def predict(request: PredictionRequest) -> PredictionResponse:
        """Predict the accessibility impact level for a road closure."""
        from packages.python.accessflow_ml.models import ImpactPredictor

        model_dir = Path(os.environ.get("ACCESSFLOW_MODEL_DIR", "data/models/impact"))

        if not model_dir.exists():
            raise HTTPException(
                status_code=503,
                detail={"code": "MODEL_UNAVAILABLE", "message": "ML model not found. Train a model first."}
            )

        try:
            predictor = await asyncio.to_thread(ImpactPredictor.load, model_dir)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "MODEL_LOAD_ERROR", "message": f"Failed to load model: {exc}"}
            ) from exc

        import pandas as pd
        df = pd.DataFrame([{
            "Type": request.type,
            "RoadClass": request.road_class,
            "DirectionsAffected": request.directions_affected,
            "WorkPeriod": request.work_period,
            "District": request.district,
            "Latitude": request.latitude,
            "Longitude": request.longitude,
            "Duration_days": request.duration_days,
            "SpecialEvent": request.special_event,
        }])

        results = await asyncio.to_thread(predictor.predict, df)
        result = results[0]

        await ws_manager.broadcast({
            "type": "prediction",
            "data": {"road": request.district, "impact": result.prediction.value, "confidence": result.confidence},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return PredictionResponse(
            prediction=result.prediction.value,
            confidence=result.confidence,
            probabilities=result.probabilities,
        )

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        if api_token:
            query_token = websocket.query_params.get("token", "")
            if not query_token or not secrets.compare_digest(query_token, api_token):
                await websocket.close(code=4401)
                return
        await ws_manager.connect(websocket)
        try:
            await websocket.send_json({"type": "status", "data": {"event": "Connected to AccessFlow live feed"}, "timestamp": datetime.now(timezone.utc).isoformat()})
            while True:
                data = await websocket.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)

    @app.get("/api/v1/route", response_model=RouteResponse, responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}, summary="Accessible pedestrian route with disruption avoidance")
    def route(origin: str = Query(..., description="Origin as 'longitude,latitude' in WGS84"), destination: str = Query(..., description="Destination as 'longitude,latitude' in WGS84"), avoid: str | None = Query(None, description="Restriction id whose candidate segments to avoid, or 'all'")) -> RouteResponse:
        """Compute baseline and disruption-avoiding walking routes on the real pedestrian network."""
        return _compute_route(origin, destination, avoid)

    @app.get("/api/v1/ai/explain", response_model=ExplanationResponse, responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}, summary="Evidence-grounded explanation (deterministic, optionally LLM-enhanced)")
    def explain(restriction_id: str | None = Query(None, description="Explain one restriction"), origin: str | None = Query(None, description="Route explanation origin 'longitude,latitude'"), destination: str | None = Query(None, description="Route explanation destination 'longitude,latitude'"), avoid: str | None = Query(None, description="Avoidance applied to the route explanation"), overview: bool = Query(False, description="Explain the whole current evidence set")) -> ExplanationResponse:
        """Generate an explanation strictly grounded in the current analytical artifacts."""
        if restriction_id:
            explanation = _explain_restriction(get_repository(), restriction_id)
        elif origin and destination:
            explanation = _explain_route(origin, destination, avoid)
        elif overview:
            explanation = _explain_overview(get_repository())
        else:
            raise HTTPException(status_code=400, detail={"code": "INVALID_EXPLANATION_CONTEXT", "message": "Provide restriction_id, origin+destination, or overview=true."})

        enhanced = _llm_enhance(explanation.kind, explanation.headline, explanation.narrative, explanation.bullets)
        if enhanced:
            explanation.narrative = enhanced
            explanation.method = "llm-enhanced-v1"
        return explanation

    # Serve the Next.js static export (built into /app/static/) at the root.
    # This must come AFTER all /api routes so it acts as a catch-all.
    _static_dir = Path(__file__).resolve().parent.parent.parent / "static"
    if _static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")

    return app


app = create_app()