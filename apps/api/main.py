"""Thin FastAPI routes over precomputed AccessFlow analytical artifacts."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from packages.python.accessflow_service import AccessFlowRepository, ArtifactUnavailableError, CsvAccessFlowRepository, DatabaseUnavailableError

try:
    from packages.python.accessflow_service import PostGISAccessFlowRepository
except (ImportError, OSError):
    PostGISAccessFlowRepository = None

from .schemas import (
    AnalyticsSummaryResponse, ErrorResponse, GeoJSONGeometry, HealthResponse,
    MatchResponse, NetworkImpactResponse, PredictionRequest, PredictionResponse,
    Provenance, RestrictionDetailResponse, RestrictionPage,
    RestrictionSummaryResponse, SpatialFeatureResponse, SpatialResponse,
    normalize_geometry,
)


VERSION = "0.1.0"


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
    origins = [origin.strip() for origin in os.environ.get("ACCESSFLOW_CORS_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET"], allow_headers=[])
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

    @app.get("/health", response_model=HealthResponse, summary="Service health")
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=VERSION)

    @app.get("/api/v1/restrictions", response_model=RestrictionPage, responses={503: {"model": ErrorResponse}}, summary="List represented restrictions")
    def list_restrictions(offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), evaluation_status: str | None = None, impact_severity: str | None = None, evidence_confidence: str | None = None, repository: AccessFlowRepository = Depends(get_repository)) -> RestrictionPage:
        items, total = repository.list_restrictions(offset=offset, limit=limit, evaluation_status=evaluation_status, impact_severity=impact_severity, evidence_confidence=evidence_confidence)
        return RestrictionPage(items=[RestrictionSummaryResponse(**item.__dict__, provenance=_provenance(item.source_snapshot)) for item in items], total=total, offset=offset, limit=limit)

    @app.get("/api/v1/restrictions/{restriction_id}", response_model=RestrictionDetailResponse, responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}, summary="Get one represented restriction")
    def restriction_detail(restriction_id: str, repository: AccessFlowRepository = Depends(get_repository)) -> RestrictionDetailResponse:
        item = repository.get_restriction(restriction_id)
        if item is None:
            raise HTTPException(status_code=404, detail={"code": "RESTRICTION_NOT_FOUND", "message": "Restriction is not represented in the available analytical artifacts."})
        return RestrictionDetailResponse(
            restriction_id=item.restriction_id, evaluation_status=item.evaluation_status,
            impact_severity=item.impact_severity, evidence_confidence=item.evidence_confidence,
            candidate_edge_count=item.candidate_edge_count, impact_evaluable=item.impact_evaluable,
            valid_restriction_polyline=item.valid_restriction_polyline,
            fallback_geometry_used=item.fallback_geometry_used, duration_hours=item.duration_hours,
            reason_codes=list(item.reason_codes), limitations=list(item.limitations),
            restriction_geometry=item.restriction_geometry, provenance=_provenance(item.source_snapshot),
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
    def predict(request: PredictionRequest) -> PredictionResponse:
        """Predict the accessibility impact level for a road closure."""
        from packages.python.accessflow_ml.models import ImpactPredictor

        model_dir = Path(os.environ.get("ACCESSFLOW_MODEL_DIR", "data/models/impact"))

        if not model_dir.exists():
            raise HTTPException(
                status_code=503,
                detail={"code": "MODEL_UNAVAILABLE", "message": "ML model not found. Train a model first."}
            )

        try:
            predictor = ImpactPredictor.load(model_dir)
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": "MODEL_LOAD_ERROR", "message": f"Failed to load model: {exc}"}
            ) from exc

        # Create DataFrame from request
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

        results = predictor.predict(df)
        result = results[0]

        return PredictionResponse(
            prediction=result.prediction.value,
            confidence=result.confidence,
            probabilities=result.probabilities,
        )

    # WebSocket connection manager
    class ConnectionManager:
        def __init__(self):
            self.active_connections: list[WebSocket] = []

        async def connect(self, websocket: WebSocket):
            await websocket.accept()
            self.active_connections.append(websocket)

        def disconnect(self, websocket: WebSocket):
            self.active_connections.remove(websocket)

        async def broadcast(self, message: dict):
            for connection in self.active_connections:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

    ws_manager = ConnectionManager()

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await ws_manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_text()
                # Echo or handle incoming messages
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)

    return app


app = create_app()