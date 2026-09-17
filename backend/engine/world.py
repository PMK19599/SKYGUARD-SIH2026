"""Deterministic World Evidence and Neighbor Coherence Layer for SKYGUARD.

Evaluates whether observed environmental changes at a target station are supported
by external world observations (spatial neighbor coherence, regional common movement,
and structured external world evidence sources).

Core Architectural Invariants:
1. Observation != Interpretation: Raw observations are never mutated.
2. Evidence != Decision: Generates candidate Evidence only; never assigns final operational states.
3. Outlier != Fault: Extreme readings are evidence of an anomaly, not proof of sensor failure.
4. Consensus != Independence: Neighbor agreement does NOT prove statistical independence.
5. Correlation != Independence: Spatial proximity or shared telemetry does not establish independent channels.
6. Target Contamination Protection: Target stations are strictly prevented from corroborating themselves.
7. Localized Weather Protection: Lack of world corroboration does NOT automatically become SENSOR evidence.
8. Zero Scenario Awareness: No simulation or ground truth labels are imported or accessed.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from backend.schemas import (
    Evidence,
    EvidenceProvenance,
    EvidenceQuality,
    EvidenceSubject,
    Observation,
)


class ExternalWorldEvidence(BaseModel):
    """Structured interface for external meteorological evidence (e.g. radar, satellite, synoptic analysis).
    
    CRITICAL PROVENANCE BOUNDARY:
    Callers cannot grant independence. Independence group naming is deterministically
    assigned by the engine and treated as unverified metadata until the M1-C5 Independence Gate.
    """

    source_id: str = Field(..., description="Identifier of external source device or service")
    source_type: str = Field(..., description="External source type: RADAR, SATELLITE, NWP_MODEL, SYNOPTIC_FRONT")
    observed_at: str = Field(..., description="ISO 8601 timestamp of external capture")
    parameter: Optional[str] = Field(None, description="Target parameter: temperature, pressure, humidity, wind")
    event_detected: bool = Field(False, description="Whether the external source indicates an environmental event")
    event_description: Optional[str] = Field(None, description="Description of the detected physical phenomenon")
    status: Literal["VALID", "MISSING", "STALE", "CONFLICTING"] = Field("VALID", description="Data lifecycle status")
    coverage: Optional[str] = Field("REGIONAL", description="Spatial coverage scale: LOCAL, REGIONAL, MESOSCALE")
    quality_rating: Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT"] = Field("HIGH", description="Quality rating")
    upstream_provider: Optional[str] = Field(None, description="Optional upstream provider/gateway identifier")


class WorldConfig(BaseModel):
    """Configuration for spatial similarity, temporal alignment, and coherence thresholds."""

    # Spatial movement similarity tolerances
    temp_similarity_tolerance_c: float = Field(2.0, description="Max deviation in delta T to be considered coherent (°C)")
    pressure_similarity_tolerance_hpa: float = Field(1.5, description="Max deviation in delta P to be considered coherent (hPa)")
    humidity_similarity_tolerance_pct: float = Field(10.0, description="Max deviation in delta RH to be considered coherent (%)")

    # Minimum delta magnitude to distinguish genuine movement from stationary noise
    min_event_delta_temp_c: float = Field(0.5, description="Minimum temperature movement to evaluate coherence (°C)")
    min_event_delta_pressure_hpa: float = Field(0.4, description="Minimum pressure movement to evaluate coherence (hPa)")
    min_event_delta_humidity_pct: float = Field(3.0, description="Minimum humidity movement to evaluate coherence (%)")

    # Spatial corroboration thresholds
    min_corroborating_stations: int = Field(2, ge=1, description="Nominal number of corroborating stations")
    stale_threshold_seconds: float = Field(1800.0, description="Maximum age of neighbor observation before marked STALE (s)")
    max_temporal_misalignment_seconds: float = Field(600.0, description="Max time delta between target and neighbor (s)")


class NeighborCoherenceDetail(BaseModel):
    """Per-neighbor evaluation detail for a specific parameter."""

    station_id: str
    observation_id: str
    source_id: str
    parameter: str
    target_delta: Optional[float] = None
    neighbor_delta: Optional[float] = None
    status: Literal["COHERENT", "CONTRADICTING", "ISOLATED", "STALE", "INCOMPLETE", "MISALIGNED"]
    description: str


class WorldEvidenceResult(BaseModel):
    """Result of world and neighbor evidence evaluation for a target station."""

    target_station_id: str
    target_observation_id: str
    evidence: List[Evidence]
    corroborating_stations: List[str]
    contradicting_stations: List[str]
    stale_stations: List[str]
    source_clusters: Dict[str, List[str]]
    has_external_corroboration: bool
    summary: str


def _parse_iso(timestamp_str: str) -> datetime:
    """Parse ISO 8601 timestamp with timezone support."""
    dt = datetime.fromisoformat(timestamp_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class WorldEvidenceEngine:
    """Deterministic engine evaluating spatial neighbor coherence and external world evidence."""

    def __init__(self, config: Optional[WorldConfig] = None) -> None:
        self.config = config or WorldConfig()

    def evaluate(
        self,
        target_obs: Observation,
        prev_target_obs: Optional[Observation] = None,
        neighbor_obs: Optional[List[Observation]] = None,
        prev_neighbor_obs: Optional[List[Observation]] = None,
        external_evidence: Optional[List[ExternalWorldEvidence]] = None,
        reference_time: Optional[datetime] = None,
    ) -> WorldEvidenceResult:
        """Evaluate spatial neighbor coherence and external world evidence for target_obs.
        
        Guarantees:
        - Target station is never allowed to corroborate itself (self-contamination protected).
        - Observations remain completely immutable.
        - Generated evidence strictly has hypothesis='WORLD'.
        - Lack of corroboration NEVER generates SENSOR evidence.
        - Different source_ids do NOT prove statistical independence (flagged for M1-C5).
        """
        # Step 1: Target self-contamination protection & deduplication
        clean_neighbors = self._filter_and_deduplicate_neighbors(target_obs, neighbor_obs or [])
        clean_prev_neighbors = self._index_observations_by_station(prev_neighbor_obs or [])

        # Step 2: Telemetry / Source Cluster Partitioning
        # Track which stations share source_ids (provenance metadata, not independence proof)
        source_clusters: Dict[str, List[str]] = {}
        for n_obs in clean_neighbors:
            src_id = n_obs.source.source_id
            source_clusters.setdefault(src_id, []).append(n_obs.station_id)

        # Step 3: Freshness & Temporal Alignment Filtering
        aligned_neighbors: List[Observation] = []
        stale_stations: List[str] = []
        target_dt = _parse_iso(target_obs.observed_at)
        ref_dt = reference_time or target_dt

        for n_obs in clean_neighbors:
            n_dt = _parse_iso(n_obs.observed_at)

            # Check staleness relative to reference time FIRST
            age = (ref_dt - n_dt).total_seconds()
            if age > self.config.stale_threshold_seconds:
                stale_stations.append(n_obs.station_id)
                continue

            # Check temporal alignment relative to target
            time_diff = abs((n_dt - target_dt).total_seconds())
            if time_diff > self.config.max_temporal_misalignment_seconds:
                continue

            aligned_neighbors.append(n_obs)

        evidence_list: List[Evidence] = []
        corroborating_stations_all: List[str] = []
        contradicting_stations_all: List[str] = []

        # Step 4: Evaluate Spatial Coherence per Parameter
        for param, tol, min_delta in [
            ("temperature_c", self.config.temp_similarity_tolerance_c, self.config.min_event_delta_temp_c),
            ("relative_humidity_pct", self.config.humidity_similarity_tolerance_pct, self.config.min_event_delta_humidity_pct),
            ("pressure_hpa", self.config.pressure_similarity_tolerance_hpa, self.config.min_event_delta_pressure_hpa),
        ]:
            param_clean = param.replace("_c", "").replace("_pct", "").replace("_hpa", "")

            # Target delta
            target_val = getattr(target_obs.measurements, param)
            prev_target_val = getattr(prev_target_obs.measurements, param) if prev_target_obs else None

            if target_val is None:
                continue

            # Determine target movement
            has_temporal_baseline = prev_target_val is not None
            target_delta = (target_val - prev_target_val) if has_temporal_baseline else 0.0
            target_has_significant_movement = has_temporal_baseline and (abs(target_delta) >= min_delta)

            # When a temporal baseline is available, only evaluate dynamic spatial coherence
            # for parameters where the target station experienced significant movement.
            # Channels that remain steady at the target station do not constitute dynamic weather events.
            if has_temporal_baseline and not target_has_significant_movement:
                continue

            # Evaluate each neighbor
            coherent_for_param: List[Observation] = []
            contradicting_for_param: List[Observation] = []

            for n_obs in aligned_neighbors:
                n_val = getattr(n_obs.measurements, param)
                if n_val is None:
                    continue

                if has_temporal_baseline:
                    prev_n_obs = clean_prev_neighbors.get(n_obs.station_id)
                    prev_n_val = getattr(prev_n_obs.measurements, param) if prev_n_obs else None

                    if prev_n_val is not None:
                        n_delta = n_val - prev_n_val
                        # Directional check
                        same_direction = (target_delta * n_delta) > 0
                        opposite_direction = (target_delta * n_delta) < 0 and (abs(n_delta) >= min_delta)
                        magnitude_diff = abs(target_delta - n_delta)

                        if same_direction and magnitude_diff <= tol:
                            coherent_for_param.append(n_obs)
                        elif opposite_direction:
                            contradicting_for_param.append(n_obs)
                else:
                    # Single snapshot envelope comparison (no temporal history)
                    if abs(target_val - n_val) <= tol:
                        coherent_for_param.append(n_obs)
                    elif abs(target_val - n_val) > (tol * 2.0):
                        contradicting_for_param.append(n_obs)

            for o in coherent_for_param:
                if o.station_id not in corroborating_stations_all:
                    corroborating_stations_all.append(o.station_id)
            for o in contradicting_for_param:
                if o.station_id not in contradicting_stations_all:
                    contradicting_stations_all.append(o.station_id)

            # Synthesize evidence for this parameter (CONSERVATIVE, NO MAJORITY VOTE)
            param_evidence = self._synthesize_spatial_evidence(
                target_obs=target_obs,
                param_name=param_clean,
                coherent_neighbors=coherent_for_param,
                contradicting_neighbors=contradicting_for_param,
                target_has_movement=target_has_significant_movement,
                target_delta=target_delta,
            )
            if param_evidence:
                evidence_list.extend(param_evidence)

        # Step 5: External World Evidence Evaluation
        has_external_corroboration = False
        if external_evidence:
            ext_ev_items = self._evaluate_external_evidence(target_obs, external_evidence, ref_dt)
            evidence_list.extend(ext_ev_items)
            if any(ev.relation == "SUPPORTS" and ev.status == "AVAILABLE" for ev in ext_ev_items):
                has_external_corroboration = True

        # Summary construction
        has_corroboration = (len(corroborating_stations_all) >= self.config.min_corroborating_stations) or has_external_corroboration
        if contradicting_stations_all and not corroborating_stations_all:
            summary = (
                f"Target {target_obs.station_id} movement is uncorroborated; "
                f"{len(contradicting_stations_all)} neighboring station(s) contradict observed pattern."
            )
        elif not corroborating_stations_all:
            summary = f"No sufficient independent WORLD corroboration for target {target_obs.station_id}."
        elif len(corroborating_stations_all) == 1:
            summary = (
                f"Target {target_obs.station_id} has 1 coherent neighbor ({corroborating_stations_all[0]}); "
                "candidate evidence only, insufficient for independent corroboration."
            )
        elif contradicting_stations_all:
            summary = (
                f"Target {target_obs.station_id} exhibits spatial conflict: "
                f"{len(corroborating_stations_all)} corroborating vs. {len(contradicting_stations_all)} contradicting neighbor(s)."
            )
        else:
            summary = (
                f"Target {target_obs.station_id} environmental pattern is spatially coherent "
                f"with {len(corroborating_stations_all)} available neighboring observations."
            )

        return WorldEvidenceResult(
            target_station_id=target_obs.station_id,
            target_observation_id=target_obs.observation_id,
            evidence=evidence_list,
            corroborating_stations=corroborating_stations_all,
            contradicting_stations=contradicting_stations_all,
            stale_stations=stale_stations,
            source_clusters=source_clusters,
            has_external_corroboration=has_external_corroboration,
            summary=summary,
        )

    # -------------------------------------------------------------------------
    # Internal Evaluation & Synthesis Helpers
    # -------------------------------------------------------------------------

    def _filter_and_deduplicate_neighbors(
        self,
        target_obs: Observation,
        neighbor_obs: List[Observation],
    ) -> List[Observation]:
        """Strictly strip target station from neighbors and deduplicate neighbor observations."""
        filtered: List[Observation] = []
        seen_stations: Dict[str, Observation] = {}
        target_id = target_obs.station_id

        for obs in neighbor_obs:
            # Rule: Target cannot corroborate itself
            if obs.station_id == target_id:
                continue

            # Deduplicate by station_id: retain newest observation if multiple supplied
            st_id = obs.station_id
            if st_id in seen_stations:
                prev_time = _parse_iso(seen_stations[st_id].observed_at)
                curr_time = _parse_iso(obs.observed_at)
                if curr_time > prev_time:
                    seen_stations[st_id] = obs
            else:
                seen_stations[st_id] = obs

        return list(seen_stations.values())

    def _index_observations_by_station(self, obs_list: List[Observation]) -> Dict[str, Observation]:
        """Index a list of observations by station_id."""
        index: Dict[str, Observation] = {}
        for o in obs_list:
            index[o.station_id] = o
        return index

    def _synthesize_spatial_evidence(
        self,
        target_obs: Observation,
        param_name: str,
        coherent_neighbors: List[Observation],
        contradicting_neighbors: List[Observation],
        target_has_movement: bool,
        target_delta: float,
    ) -> List[Evidence]:
        """Synthesize candidate Evidence adhering to strict non-consensus invariants."""
        # Critical Rule: If there is no movement on target, or zero coherent neighbors, do not emit ungrounded WORLD evidence
        n_coherent = len(coherent_neighbors)
        n_contradicting = len(contradicting_neighbors)

        if n_coherent == 0 and n_contradicting == 0:
            return []

        evidence_items: List[Evidence] = []
        derived_ids = [target_obs.observation_id] + [o.observation_id for o in coherent_neighbors] + [o.observation_id for o in contradicting_neighbors]

        # Case A: Spatial Contradiction (neighbors actively contradict target movement)
        if n_contradicting > 0 and n_coherent == 0:
            evidence_items.append(
                Evidence(
                    evidence_id=f"ev-world-{target_obs.observation_id}-contra-{param_name}",
                    subject=EvidenceSubject(
                        station_id=target_obs.station_id,
                        observation_ids=derived_ids,
                    ),
                    type="SPATIAL",
                    relation="CONTRADICTS",
                    hypothesis="WORLD",
                    description=(
                        f"Spatial contradiction on {param_name}: {n_contradicting} neighbor station(s) contradict "
                        f"observed target change ({target_delta:+.2f})."
                    ),
                    strength=0.75,
                    quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                    provenance=EvidenceProvenance(
                        source_type="DERIVED",
                        source_id="world-spatial-v1",
                        derived_from=derived_ids,
                    ),
                    independence_group=f"spatial-contradiction-{param_name}",
                    status="AVAILABLE",
                )
            )
            return evidence_items

        # Case B: Conflicting Evidence (some neighbors agree, others contradict -> NO naive majority vote)
        if n_contradicting > 0 and n_coherent > 0:
            evidence_items.append(
                Evidence(
                    evidence_id=f"ev-world-{target_obs.observation_id}-conflict-{param_name}",
                    subject=EvidenceSubject(
                        station_id=target_obs.station_id,
                        observation_ids=derived_ids,
                    ),
                    type="SPATIAL",
                    relation="SUPPORTS",
                    hypothesis="WORLD",
                    description=(
                        f"Spatial conflict detected on {param_name}: {n_coherent} neighbor(s) coherent but "
                        f"{n_contradicting} contradict. Heuristic support severely discounted; no consensus assumed."
                    ),
                    strength=0.25,  # Heavily discounted due to active contradiction
                    quality=EvidenceQuality(status="DEGRADED", freshness="FRESH", completeness="PARTIAL"),
                    provenance=EvidenceProvenance(
                        source_type="DERIVED",
                        source_id="world-spatial-v1",
                        derived_from=derived_ids,
                    ),
                    independence_group=f"spatial-conflict-{param_name}",
                    status="AVAILABLE",
                )
            )
            return evidence_items

        # Case C: 1 Neighbor Only -> Explicitly weak candidate evidence, insufficient alone
        if n_coherent == 1:
            n_single = coherent_neighbors[0]
            evidence_items.append(
                Evidence(
                    evidence_id=f"ev-world-{target_obs.observation_id}-single-{param_name}",
                    subject=EvidenceSubject(
                        station_id=target_obs.station_id,
                        observation_ids=[target_obs.observation_id, n_single.observation_id],
                    ),
                    type="SPATIAL",
                    relation="SUPPORTS",
                    hypothesis="WORLD",
                    description=(
                        f"Single neighbor {n_single.station_id} is spatially/temporally coherent on {param_name}; "
                        "candidate evidence only, insufficient for independent corroboration."
                    ),
                    strength=0.35,  # Explicitly weak
                    quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="PARTIAL"),
                    provenance=EvidenceProvenance(
                        source_type="DERIVED",
                        source_id="world-spatial-v1",
                        derived_from=[target_obs.observation_id, n_single.observation_id],
                    ),
                    independence_group=f"spatial-single-neighbor-{param_name}",
                    status="AVAILABLE",
                )
            )
            return evidence_items

        # Case D: >= 2 Neighbors Coherent
        # Inspect source clusters among coherent neighbors
        source_clusters: Dict[str, List[str]] = {}
        for o in coherent_neighbors:
            source_clusters.setdefault(o.source.source_id, []).append(o.station_id)

        distinct_clusters = len(source_clusters)
        all_coherent_ids = [o.station_id for o in coherent_neighbors]

        if distinct_clusters == 1:
            # All coherent neighbors share identical source path -> single provenance cluster
            src_name = list(source_clusters.keys())[0]
            evidence_items.append(
                Evidence(
                    evidence_id=f"ev-world-{target_obs.observation_id}-cluster-{param_name}",
                    subject=EvidenceSubject(
                        station_id=target_obs.station_id,
                        observation_ids=derived_ids,
                    ),
                    type="SPATIAL",
                    relation="SUPPORTS",
                    hypothesis="WORLD",
                    description=(
                        f"Coherent movement on {param_name} with {n_coherent} neighbors ({', '.join(all_coherent_ids)}) "
                        f"sharing common telemetry source '{src_name}'. Single provenance cluster; statistical independence not established."
                    ),
                    strength=0.50,  # Moderate strength; explicitly constrained by shared source
                    quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                    provenance=EvidenceProvenance(
                        source_type="DERIVED",
                        source_id="world-spatial-v1",
                        derived_from=derived_ids,
                    ),
                    independence_group=f"spatial-cluster-{src_name}-{param_name}",
                    status="AVAILABLE",
                )
            )
        else:
            # Multiple distinct source clusters corroborated
            evidence_items.append(
                Evidence(
                    evidence_id=f"ev-world-{target_obs.observation_id}-multicluster-{param_name}",
                    subject=EvidenceSubject(
                        station_id=target_obs.station_id,
                        observation_ids=derived_ids,
                    ),
                    type="SPATIAL",
                    relation="SUPPORTS",
                    hypothesis="WORLD",
                    description=(
                        f"Spatially/temporally coherent environmental movement on {param_name} corroborated by {n_coherent} "
                        f"neighbors ({', '.join(all_coherent_ids)}) across {distinct_clusters} distinct source clusters. "
                        "Candidate WORLD evidence; physical independence subject to downstream verification."
                    ),
                    strength=0.80,
                    quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                    provenance=EvidenceProvenance(
                        source_type="DERIVED",
                        source_id="world-spatial-v1",
                        derived_from=derived_ids,
                    ),
                    independence_group=f"spatial-multicluster-{param_name}",
                    status="AVAILABLE",
                )
            )

        return evidence_items

    def _evaluate_external_evidence(
        self,
        target_obs: Observation,
        external_evidence: List[ExternalWorldEvidence],
        ref_dt: datetime,
    ) -> List[Evidence]:
        """Evaluate structured external world sources with hard provenance boundaries."""
        ext_evidence_items: List[Evidence] = []

        for item in external_evidence:
            # Deterministic namespace partition: never permit caller-injected "independent" claims
            indep_group = f"external-source-{item.source_type.lower()}-{item.source_id.lower()}"

            if item.status == "VALID" and item.event_detected:
                # Check freshness of external observation
                try:
                    ext_dt = _parse_iso(item.observed_at)
                    age_seconds = abs((ref_dt - ext_dt).total_seconds())
                except Exception:
                    age_seconds = 0.0

                freshness: Literal["FRESH", "STALE", "EXPIRED"] = (
                    "FRESH" if age_seconds <= self.config.stale_threshold_seconds else "STALE"
                )

                if freshness == "STALE":
                    # Stale external evidence is not treated as strong candidate evidence
                    ext_evidence_items.append(
                        Evidence(
                            evidence_id=f"ev-ext-{target_obs.observation_id}-{item.source_id}-stale",
                            subject=EvidenceSubject(
                                station_id=target_obs.station_id,
                                observation_ids=[target_obs.observation_id],
                            ),
                            type="SPATIAL",
                            relation="SUPPORTS",
                            hypothesis="WORLD",
                            description=(
                                f"External {item.source_type} source '{item.source_id}' indicates event but observation is STALE "
                                f"({age_seconds:.0f}s old). Candidate weight discounted."
                            ),
                            strength=0.20,
                            quality=EvidenceQuality(status="DEGRADED", freshness="STALE", completeness="COMPLETE"),
                            provenance=EvidenceProvenance(
                                source_type="DERIVED",
                                source_id=item.source_id,
                                derived_from=[target_obs.observation_id],
                            ),
                            independence_group=indep_group,
                            status="SUPPRESSED",
                        )
                    )
                else:
                    # Valid fresh external event detection
                    ext_evidence_items.append(
                        Evidence(
                            evidence_id=f"ev-ext-{target_obs.observation_id}-{item.source_id}",
                            subject=EvidenceSubject(
                                station_id=target_obs.station_id,
                                observation_ids=[target_obs.observation_id],
                            ),
                            type="SPATIAL",
                            relation="SUPPORTS",
                            hypothesis="WORLD",
                            description=(
                                f"External {item.source_type} source '{item.source_id}' detected physical atmospheric event: "
                                f"{item.event_description or 'event active'}. Provenance preserved; independence unverified."
                            ),
                            strength=0.70,
                            quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                            provenance=EvidenceProvenance(
                                source_type="DERIVED",
                                source_id=item.source_id,
                                derived_from=[target_obs.observation_id],
                            ),
                            independence_group=indep_group,
                            status="AVAILABLE",
                        )
                    )
            elif item.status == "CONFLICTING":
                # External source contradicts event hypothesis
                ext_evidence_items.append(
                    Evidence(
                        evidence_id=f"ev-ext-{target_obs.observation_id}-{item.source_id}-conflict",
                        subject=EvidenceSubject(
                            station_id=target_obs.station_id,
                            observation_ids=[target_obs.observation_id],
                        ),
                        type="SPATIAL",
                        relation="CONTRADICTS",
                        hypothesis="WORLD",
                        description=(
                            f"External {item.source_type} source '{item.source_id}' contradicts environmental event: "
                            f"{item.event_description or 'baseline clear'}."
                        ),
                        strength=0.65,
                        quality=EvidenceQuality(status="VALID", freshness="FRESH", completeness="COMPLETE"),
                        provenance=EvidenceProvenance(
                            source_type="DERIVED",
                            source_id=item.source_id,
                            derived_from=[target_obs.observation_id],
                        ),
                        independence_group=indep_group,
                        status="AVAILABLE",
                    )
                )

        return ext_evidence_items
