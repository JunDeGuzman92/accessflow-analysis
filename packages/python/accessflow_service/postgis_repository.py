"""Production-oriented PostgreSQL/PostGIS repository for AccessFlow artifacts."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Iterable

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String, Text, delete, func, select, text
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .models import CandidateMatch, NetworkImpact, RestrictionDetail, RestrictionSummary
from .repository import ArtifactUnavailableError, DatabaseUnavailableError


def _load_spatial_artifact(artifact_path: Path) -> dict[str, Any]:
    """Lazy import of spatial artifacts."""
    try:
        from packages.python.accessflow_spatial.artifacts import load_spatial_artifact
        return load_spatial_artifact(artifact_path)
    except (ImportError, OSError):
        return {"records": {}}


class Base(DeclarativeBase):
    pass


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"

    snapshot_id: Mapped[str] = mapped_column(Text, primary_key=True)
    publisher: Mapped[str] = mapped_column(String(255), default="Toronto Open Data")
    analytical_status: Mapped[str] = mapped_column(String(255), default="RESEARCH_ORIENTED_CANDIDATE_ANALYSIS")
    methodology_version: Mapped[str] = mapped_column(String(255), default="phase15-replacement-path-v1")
    checksum: Mapped[str | None] = mapped_column(String(255), nullable=True)

    restrictions: Mapped[list["RestrictionRecord"]] = relationship(back_populates="snapshot")


class RestrictionRecord(Base):
    __tablename__ = "restrictions"

    restriction_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    evaluation_status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    impact_severity: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    evidence_confidence: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    candidate_edge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    impact_evaluable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_snapshot: Mapped[str] = mapped_column(Text, ForeignKey("source_snapshots.snapshot_id"), nullable=False, index=True)
    valid_restriction_polyline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fallback_geometry_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duration_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason_codes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    limitations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    restriction_geometry: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    geometry: Mapped[Any | None] = mapped_column(Geometry("GEOMETRY", srid=4326, spatial_index=False), nullable=True)

    # ORM relationships let SQLAlchemy order inserts/deletes so that this parent
    # row is written before (and removed after) its dependent child rows.
    matches: Mapped[list["RestrictionMatchRecord"]] = relationship(
        back_populates="restriction", cascade="all, delete-orphan"
    )
    network_impacts: Mapped[list["NetworkImpactRecord"]] = relationship(
        back_populates="restriction", cascade="all, delete-orphan"
    )
    snapshot: Mapped["SourceSnapshot"] = relationship(back_populates="restrictions")


class RestrictionMatchRecord(Base):
    __tablename__ = "restriction_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    restriction_id: Mapped[str] = mapped_column(String(128), ForeignKey("restrictions.restriction_id"), nullable=False, index=True)
    pedestrian_feature_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    match_type: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_confidence: Mapped[str] = mapped_column(String(64), nullable=False)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    candidate_status: Mapped[str] = mapped_column(String(64), nullable=False, default="CANDIDATE_AFFECTED_SEGMENT")
    geometry: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    restriction: Mapped["RestrictionRecord"] = relationship(back_populates="matches")


class NetworkImpactRecord(Base):
    __tablename__ = "network_impacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    restriction_id: Mapped[str] = mapped_column(String(128), ForeignKey("restrictions.restriction_id"), nullable=False, index=True)
    scenario: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_status: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_edge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluated_edge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alternative_path_edge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    local_connectivity_loss_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    local_connectivity_loss_fraction: Mapped[float | None] = mapped_column(Float, nullable=True)
    median_replacement_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_replacement_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    median_added_replacement_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_added_replacement_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    set_evaluation_status: Mapped[str] = mapped_column(String(64), nullable=False)
    set_component_increase: Mapped[int | None] = mapped_column(Integer, nullable=True)
    set_disconnected_boundary_pair_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    limitations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    restriction: Mapped["RestrictionRecord"] = relationship(back_populates="network_impacts")


def _normalize_database_url(database_url: str) -> str:
    cleaned = database_url.strip()
    if cleaned.startswith("postgresql://") and "+psycopg" not in cleaned:
        return cleaned.replace("postgresql://", "postgresql+psycopg://", 1)
    return cleaned


def _coerce_number(value: str | None) -> float | None:
    return float(value) if value not in {None, ""} else None


def _coerce_integer(value: str | None) -> int | None:
    return int(float(value)) if value not in {None, ""} else None


def _coerce_boolean(value: str | None) -> bool:
    return value == "True"


def _coerce_codes(value: str | None) -> tuple[str, ...]:
    return tuple(item for item in (value or "").split(";") if item)


class PostGISAccessFlowRepository:
    """Repository implementation backed by PostgreSQL/PostGIS. It supports CSV bootstrapping for deterministic startup and reloads."""

    def __init__(self, database_url: str | None = None, *, data_dir: str | Path | None = None, create_schema: bool = True) -> None:
        self.database_url = _normalize_database_url(database_url or os.environ.get("DATABASE_URL", ""))
        if not self.database_url:
            raise DatabaseUnavailableError("DATABASE_URL must be configured to use the PostGIS repository.")
        self.engine = create_engine(self.database_url, future=True, pool_pre_ping=True)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.data_dir = Path(data_dir) if data_dir is not None else Path(os.environ.get("ACCESSFLOW_ANALYTICS_DIR", "data/processed"))
        spatial_path = self.data_dir / "phase22-spatial.json"
        self._spatial = _load_spatial_artifact(spatial_path) if spatial_path.exists() else {"records": {}}
        if create_schema:
            self.initialize_database()
            self._bootstrap_if_artifacts_exist()

    @classmethod
    def from_environment(cls, *, data_dir: str | Path | None = None) -> "PostGISAccessFlowRepository":
        return cls(database_url=os.environ.get("DATABASE_URL"), data_dir=data_dir)

    def initialize_database(self) -> None:
        try:
            with self.engine.begin() as connection:
                if connection.dialect.name == "postgresql":
                    connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            Base.metadata.create_all(self.engine)
        except Exception as exc:  # pragma: no cover - surfaced as configuration error
            raise DatabaseUnavailableError(f"Unable to initialize PostGIS database: {exc}") from exc

    def _bootstrap_if_artifacts_exist(self) -> None:
        cohort = self.data_dir / "phase14-evaluation-cohort.csv"
        edges = self.data_dir / "phase15-edge-replacement.csv"
        impacts = self.data_dir / "phase15-restriction-impact.csv"
        if not cohort.exists() or not edges.exists() or not impacts.exists():
            return
        self.load_from_artifacts(self.data_dir)

    def load_from_artifacts(self, data_dir: str | Path, *, snapshot: str | None = None) -> None:
        directory = Path(data_dir)
        spatial_path = directory / "phase22-spatial.json"
        self._spatial = _load_spatial_artifact(spatial_path) if spatial_path.exists() else {"records": {}}
        cohort = directory / "phase14-evaluation-cohort.csv"
        edges = directory / "phase15-edge-replacement.csv"
        impacts = directory / "phase15-restriction-impact.csv"
        missing = [path.name for path in (cohort, edges, impacts) if not path.exists()]
        if missing:
            raise ArtifactUnavailableError(f"Required analytical artifacts are unavailable: {', '.join(missing)}")

        with cohort.open("r", encoding="utf-8", newline="") as source:
            restriction_rows = list(csv.DictReader(source))
        with edges.open("r", encoding="utf-8", newline="") as source:
            edge_rows = list(csv.DictReader(source))
        with impacts.open("r", encoding="utf-8", newline="") as source:
            impact_rows = list(csv.DictReader(source))

        snapshot_name = snapshot or (restriction_rows[0].get("source_snapshot") if restriction_rows else "phase15-replacement-path-v1")
        with Session(self.engine) as session:
            restriction_ids = [row["restriction_id"] for row in restriction_rows]
            if restriction_ids:
                session.execute(delete(RestrictionMatchRecord).where(RestrictionMatchRecord.restriction_id.in_(restriction_ids)))
                session.execute(delete(NetworkImpactRecord).where(NetworkImpactRecord.restriction_id.in_(restriction_ids)))
                session.execute(delete(RestrictionRecord).where(RestrictionRecord.source_snapshot == snapshot_name))
                session.execute(delete(SourceSnapshot).where(SourceSnapshot.snapshot_id == snapshot_name))

            session.add(SourceSnapshot(snapshot_id=snapshot_name, publisher="Toronto Open Data", analytical_status="RESEARCH_ORIENTED_CANDIDATE_ANALYSIS", methodology_version="phase15-replacement-path-v1"))

            for row in restriction_rows:
                session.add(RestrictionRecord(
                    restriction_id=row["restriction_id"],
                    evaluation_status=row["evaluation_status"],
                    impact_severity=row["impact_severity"],
                    evidence_confidence=row["evidence_confidence"],
                    candidate_edge_count=int(row["candidate_edge_count"]),
                    impact_evaluable=_coerce_boolean(row.get("impact_evaluable")),
                    source_snapshot=snapshot_name,
                    valid_restriction_polyline=_coerce_boolean(row.get("valid_restriction_polyline")),
                    fallback_geometry_used=_coerce_boolean(row.get("fallback_geometry_used")),
                    duration_hours=_coerce_number(row.get("duration_hours")),
                    reason_codes=list(_coerce_codes(row.get("reason_codes"))),
                    limitations=list(_coerce_codes(row.get("limitations"))),
                    restriction_geometry=None,
                ))

            for row in edge_rows:
                session.add(RestrictionMatchRecord(
                    restriction_id=row["restriction_id"],
                    pedestrian_feature_id=row["source_segment_id"],
                    match_type=row["match_type"],
                    evidence_confidence=row["evidence_confidence"],
                    distance_m=_coerce_number(row.get("distance_m")),
                    candidate_status="CANDIDATE_AFFECTED_SEGMENT",
                    geometry=None,
                ))

            for row in impact_rows:
                session.add(NetworkImpactRecord(
                    restriction_id=row["restriction_id"],
                    scenario=row["scenario"],
                    evaluation_status=row["evaluation_state"],
                    candidate_edge_count=int(float(row["candidate_edge_count"])),
                    evaluated_edge_count=int(float(row["evaluated_edge_count"])),
                    alternative_path_edge_count=int(float(row["alternative_path_edge_count"])),
                    local_connectivity_loss_count=int(float(row["local_connectivity_loss_count"])),
                    local_connectivity_loss_fraction=_coerce_number(row.get("local_connectivity_loss_fraction")),
                    median_replacement_ratio=_coerce_number(row.get("median_replacement_ratio")),
                    max_replacement_ratio=_coerce_number(row.get("max_replacement_ratio")),
                    median_added_replacement_distance_m=_coerce_number(row.get("median_added_replacement_distance_m")),
                    max_added_replacement_distance_m=_coerce_number(row.get("max_added_replacement_distance_m")),
                    set_evaluation_status=row["set_evaluation_state"],
                    set_component_increase=_coerce_integer(row.get("restriction_set_component_increase")),
                    set_disconnected_boundary_pair_count=_coerce_integer(row.get("restriction_set_disconnected_boundary_pair_count")),
                    limitations=("GEOMETRY_DERIVED_CITY_ROUTING_TOPOLOGY_NOT_AVAILABLE", "CANDIDATE_SEGMENTS_ARE_NOT_CONFIRMED_CLOSURES"),
                ))

            session.commit()

    def _summary(self, record: RestrictionRecord) -> RestrictionSummary:
        return RestrictionSummary(
            restriction_id=record.restriction_id,
            evaluation_status=record.evaluation_status,
            impact_severity=record.impact_severity,
            evidence_confidence=record.evidence_confidence,
            candidate_edge_count=record.candidate_edge_count,
            impact_evaluable=record.impact_evaluable,
            source_snapshot=record.source_snapshot,
            match_type=getattr(record, 'match_type', None),
            duration_hours=getattr(record, 'duration_hours', None),
        )

    def list_restrictions(self, *, offset: int, limit: int, evaluation_status: str | None, impact_severity: str | None, evidence_confidence: str | None) -> tuple[list[RestrictionSummary], int]:
        with Session(self.engine) as session:
            statement = select(RestrictionRecord)
            if evaluation_status is not None:
                statement = statement.where(RestrictionRecord.evaluation_status == evaluation_status)
            if impact_severity is not None:
                statement = statement.where(RestrictionRecord.impact_severity == impact_severity)
            if evidence_confidence is not None:
                statement = statement.where(RestrictionRecord.evidence_confidence == evidence_confidence)
            statement = statement.order_by(RestrictionRecord.restriction_id.asc())
            records = list(session.execute(statement).scalars().all())
            total = len(records)
            return [self._summary(record) for record in records[offset:offset + limit]], total

    def get_restriction(self, restriction_id: str) -> RestrictionDetail | None:
        with Session(self.engine) as session:
            record = session.get(RestrictionRecord, restriction_id)
            if record is None:
                return None
            summary = self._summary(record)
            spatial = self._spatial["records"].get(restriction_id, {})
            return RestrictionDetail(**summary.__dict__, valid_restriction_polyline=record.valid_restriction_polyline, fallback_geometry_used=record.fallback_geometry_used, duration_hours=record.duration_hours, reason_codes=tuple(record.reason_codes or ()), limitations=tuple(record.limitations or ()), restriction_geometry=spatial.get("restriction_geometry", record.restriction_geometry))

    def get_matches(self, restriction_id: str) -> list[CandidateMatch] | None:
        with Session(self.engine) as session:
            statement = select(RestrictionMatchRecord).where(RestrictionMatchRecord.restriction_id == restriction_id)
            rows = list(session.execute(statement).scalars().all())
            if not rows:
                if session.get(RestrictionRecord, restriction_id) is None:
                    return None
                return []
            spatial_matches = self._spatial["records"].get(restriction_id, {}).get("matches", [])
            return [CandidateMatch(
                restriction_id=row.restriction_id,
                pedestrian_feature_id=row.pedestrian_feature_id,
                match_type=row.match_type,
                evidence_confidence=row.evidence_confidence,
                distance_m=row.distance_m,
                candidate_status=row.candidate_status,
                geometry=next((item.get("geometry") for item in spatial_matches if item.get("feature_id") == row.pedestrian_feature_id), row.geometry),
                source=next((item.get("source") for item in spatial_matches if item.get("feature_id") == row.pedestrian_feature_id), None),
                candidate_rank=next((item.get("candidate_rank") for item in spatial_matches if item.get("feature_id") == row.pedestrian_feature_id), None),
            ) for row in sorted(rows, key=lambda item: item.pedestrian_feature_id)]

    def get_spatial_artifact(self, restriction_id: str) -> dict[str, object] | None:
        with Session(self.engine) as session:
            if session.get(RestrictionRecord, restriction_id) is None:
                return None
        return self._spatial["records"].get(restriction_id, {})

    def get_network_impact(self, restriction_id: str) -> list[NetworkImpact] | None:
        with Session(self.engine) as session:
            statement = select(NetworkImpactRecord).where(NetworkImpactRecord.restriction_id == restriction_id)
            rows = list(session.execute(statement).scalars().all())
            if not rows:
                if session.get(RestrictionRecord, restriction_id) is None:
                    return None
                return []
            return [NetworkImpact(
                restriction_id=row.restriction_id,
                scenario=row.scenario,
                evaluation_status=row.evaluation_status,
                candidate_edge_count=row.candidate_edge_count,
                evaluated_edge_count=row.evaluated_edge_count,
                alternative_path_edge_count=row.alternative_path_edge_count,
                local_connectivity_loss_count=row.local_connectivity_loss_count,
                local_connectivity_loss_fraction=row.local_connectivity_loss_fraction,
                median_replacement_ratio=row.median_replacement_ratio,
                max_replacement_ratio=row.max_replacement_ratio,
                median_added_replacement_distance_m=row.median_added_replacement_distance_m,
                max_added_replacement_distance_m=row.max_added_replacement_distance_m,
                set_evaluation_status=row.set_evaluation_status,
                set_component_increase=row.set_component_increase,
                set_disconnected_boundary_pair_count=row.set_disconnected_boundary_pair_count,
                limitations=tuple(row.limitations or ()),
            ) for row in rows]

    def analytics_summary(self) -> dict[str, object]:
        with Session(self.engine) as session:
            records = list(session.execute(select(RestrictionRecord).order_by(RestrictionRecord.restriction_id.asc())).scalars().all())
            if not records:
                return {
                    "total_restrictions_represented": 0,
                    "evaluation_status_distribution": {},
                    "impact_severity_distribution": {},
                    "evidence_confidence_distribution": {},
                    "evaluated_restrictions": 0,
                }
            def counts(items: Iterable[str]) -> dict[str, int]:
                output: dict[str, int] = {}
                for value in sorted(set(items)):
                    output[value] = list(items).count(value)
                return output
            values = [item.evaluation_status for item in records]
            impact_values = [item.impact_severity for item in records]
            evidence_values = [item.evidence_confidence for item in records]
            return {
                "total_restrictions_represented": len(records),
                "evaluation_status_distribution": counts(values),
                "impact_severity_distribution": counts(impact_values),
                "evidence_confidence_distribution": counts(evidence_values),
                "evaluated_restrictions": sum(1 for item in records if item.impact_evaluable),
            }
