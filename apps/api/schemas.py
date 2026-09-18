"""Public Pydantic API contracts."""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, Field


class Provenance(BaseModel):
    publisher: str = "Toronto Open Data"
    analytical_status: str = "RESEARCH_ORIENTED_CANDIDATE_ANALYSIS"
    methodology_version: str = "phase15-replacement-path-v1"
    source_snapshot: str | None = Field(None, description="Manifest checksum identity; never a local path.")


GeometryType = Literal["Point", "LineString", "MultiLineString"]


class GeoJSONGeometry(BaseModel):
    type: GeometryType
    coordinates: list[Any]


def _coordinate_pair(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(isinstance(item, (int, float)) and math.isfinite(item) for item in value)


def normalize_geometry(value: Any) -> dict[str, Any] | None:
    """Return only supported WGS84 GeoJSON shapes; malformed source values stay null."""
    if not isinstance(value, dict) or value.get("type") not in {"Point", "LineString", "MultiLineString"}:
        return None
    coordinates = value.get("coordinates")
    geometry_type = value["type"]
    if geometry_type == "Point" and _coordinate_pair(coordinates):
        return {"type": geometry_type, "coordinates": coordinates}
    if geometry_type == "LineString" and isinstance(coordinates, list) and len(coordinates) >= 2 and all(_coordinate_pair(item) for item in coordinates):
        return {"type": geometry_type, "coordinates": coordinates}
    if geometry_type == "MultiLineString" and isinstance(coordinates, list) and coordinates and all(isinstance(line, list) and len(line) >= 2 and all(_coordinate_pair(item) for item in line) for line in coordinates):
        return {"type": geometry_type, "coordinates": coordinates}
    return None


class RestrictionSummaryResponse(BaseModel):
    restriction_id: str
    evaluation_status: str
    impact_severity: str
    evidence_confidence: str
    candidate_edge_count: int
    impact_evaluable: bool
    provenance: Provenance


class RestrictionDetailResponse(RestrictionSummaryResponse):
    valid_restriction_polyline: bool
    fallback_geometry_used: bool
    duration_hours: float | None
    reason_codes: list[str]
    limitations: list[str]
    restriction_geometry: dict[str, Any] | None = Field(None, description="Optional GeoJSON in EPSG:4326; unavailable in the Phase 16 CSV artifacts.")


class MatchResponse(BaseModel):
    pedestrian_feature_id: str
    match_type: str
    evidence_confidence: str
    distance_m: float | None
    candidate_status: str = "CANDIDATE_AFFECTED_SEGMENT"
    geometry: dict[str, Any] | None = Field(None, description="Optional candidate GeoJSON in EPSG:4326; never projected metric coordinates.")


class SpatialFeatureResponse(BaseModel):
    feature_id: str
    geometry: GeoJSONGeometry | None
    match_type: str
    confidence: str
    distance_m: float | None
    source: str | None
    candidate_rank: int | None
    candidate_status: str


class SpatialResponse(BaseModel):
    restriction_id: str
    restriction_geometry: GeoJSONGeometry | None
    matched_features: list[SpatialFeatureResponse]
    candidate_features: list[SpatialFeatureResponse]
    crs: str
    evidence_confidence: str
    geometry_status: Literal["AVAILABLE", "PARTIAL", "NOT_AVAILABLE"]
    provenance: Provenance


class NetworkImpactResponse(BaseModel):
    scenario: str
    evaluation_status: str
    candidate_edge_count: int
    evaluated_edge_count: int
    alternative_path_edge_count: int
    local_connectivity_loss_count: int
    local_connectivity_loss_fraction: float | None
    median_replacement_ratio: float | None
    max_replacement_ratio: float | None
    median_added_replacement_distance_m: float | None
    max_added_replacement_distance_m: float | None
    set_evaluation_status: str
    set_component_increase: int | None
    set_disconnected_boundary_pair_count: int | None
    limitations: list[str]
    provenance: Provenance


class ErrorResponse(BaseModel):
    code: str
    message: str


class RestrictionPage(BaseModel):
    items: list[RestrictionSummaryResponse]
    total: int
    offset: int
    limit: int


class HealthResponse(BaseModel):
    status: str
    version: str


class AnalyticsSummaryResponse(BaseModel):
    total_restrictions_represented: int
    evaluated_restrictions: int
    evaluation_status_distribution: dict[str, int]
    impact_severity_distribution: dict[str, int]
    evidence_confidence_distribution: dict[str, int]
    provenance: Provenance


class PredictionRequest(BaseModel):
    """Request to predict accessibility impact for a road closure."""
    type: str = Field(..., description="Closure type (CONSTRUCTION, ROAD_CLOSED)")
    road_class: str = Field(..., description="Road classification (Major Arterial Road, Local Road, etc.)")
    directions_affected: str = Field(..., description="Directions affected (BOTH_DIRECTIONS, ONE_DIRECTION)")
    work_period: str = Field(..., description="Work period (Continuous, Daily, Weekdays, etc.)")
    district: str = Field(..., description="City district")
    latitude: float = Field(..., description="Latitude (WGS84)")
    longitude: float = Field(..., description="Longitude (WGS84)")
    duration_days: float = Field(..., description="Duration in days")
    special_event: str = Field("No", description="Special event flag (Yes/No)")


class PredictionResponse(BaseModel):
    """Response with predicted accessibility impact."""
    prediction: str = Field(..., description="Predicted impact level (None, Low, High)")
    confidence: float = Field(..., description="Prediction confidence (0-1)")
    probabilities: dict[str, float] = Field(..., description="Probability for each class")