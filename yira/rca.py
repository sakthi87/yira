from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import CausalChain, LogEvent, RootCauseScore, Signal


def score_root_causes(
    config: dict[str, Any],
    signals: list[Signal],
    log_events: list[LogEvent],
    causal_chains: list[CausalChain] | None = None,
) -> list[RootCauseScore]:
    signal_scores = build_signal_score_map(signals)
    enrich_with_causal_scores(signal_scores, causal_chains or [])
    log_scores = build_log_score_map(log_events)
    combined = {**signal_scores}
    for name, score in log_scores.items():
        combined[name] = max(combined.get(name, 0.0), score)

    scores: list[RootCauseScore] = []
    for category, definition in config.get("root_causes", {}).items():
        if definition.get("enabled", True) is False:
            continue
        weights = definition.get("weights", {})
        if not weights:
            continue
        weighted_total = 0.0
        weight_total = 0.0
        evidence: list[str] = []
        matched_signals: list[str] = []
        for evidence_name, weight in weights.items():
            weight = float(weight)
            evidence_score = combined.get(evidence_name, 0.0)
            weighted_total += evidence_score * weight
            weight_total += weight
            if evidence_score > 0:
                matched_signals.append(evidence_name)
                evidence.append(f"{evidence_name} score={evidence_score:.2f} weight={weight:.2f}")
        if weight_total == 0:
            continue
        score = min(weighted_total / weight_total, 1.0)
        score = min(score + root_cause_causal_boost(category, causal_chains or []), 1.0)
        if score <= 0 and not evidence:
            continue
        threshold = float(definition.get("threshold", 0.7))
        scores.append(
            RootCauseScore(
                category=category,
                score=score,
                confidence_band=confidence_band(config, score),
                threshold=threshold,
                evidence=evidence,
                signals=matched_signals,
                recommendations=definition.get("recommendations", []),
            )
        )
    return sorted(scores, key=lambda item: (-item.score, item.category))


def build_signal_score_map(signals: list[Signal]) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for signal in signals:
        names = {signal.name, signal.category, *getattr(signal, "categories", [])}
        for label in signal.labels.values():
            if label:
                names.add(label)
        enhanced_score = min(signal.score + duration_boost(signal) + spread_boost(signal), 1.0)
        for name in names:
            scores[name] = max(scores[name], enhanced_score)
    return dict(scores)


def duration_boost(signal: Signal) -> float:
    duration_seconds = getattr(signal, "duration_seconds", 0)
    if duration_seconds >= 300:
        return 0.08
    if duration_seconds >= 120:
        return 0.05
    if duration_seconds >= 60:
        return 0.03
    return 0.0


def spread_boost(signal: Signal) -> float:
    entity_count = len(getattr(signal, "affected_nodes", [])) + len(getattr(signal, "affected_regions", []))
    if entity_count >= 5:
        return 0.05
    if entity_count >= 2:
        return 0.03
    return 0.0


def enrich_with_causal_scores(scores: dict[str, float], causal_chains: list[CausalChain]) -> None:
    for chain in causal_chains:
        causal_score = min(chain.confidence, 1.0)
        scores[f"causal_chain:{chain.name}"] = max(scores.get(f"causal_chain:{chain.name}", 0.0), causal_score)
        for edge in chain.edges:
            scores[edge.source_category] = max(scores.get(edge.source_category, 0.0), min(causal_score + 0.05, 1.0))
            scores[edge.target_category] = max(scores.get(edge.target_category, 0.0), min(causal_score + 0.05, 1.0))


def root_cause_causal_boost(category: str, causal_chains: list[CausalChain]) -> float:
    if not causal_chains:
        return 0.0
    mapping = {
        "replication_delay": ("write_pressure_to_read_latency", "storage_to_replication_delay", "network_to_raft_delay"),
        "rpc_saturation": ("rpc_queue_to_read_latency", "hotspot_to_queue_and_latency"),
        "network_instability": ("network_to_raft_delay",),
        "workload_pressure": ("write_pressure_to_read_latency", "hotspot_to_queue_and_latency"),
        "storage_bottleneck": ("storage_to_replication_delay",),
        "master_pressure": ("master_lookup_to_ysql_latency",),
        "transaction_contention": ("transaction_contention_to_latency",),
        "memory_or_cache_pressure": ("docdb_read_path_to_ysql_latency",),
        "docdb_read_path_pressure": ("docdb_read_path_to_ysql_latency",),
        "raft_or_leader_instability": ("network_to_raft_delay", "write_pressure_to_read_latency"),
        "consistency_wait_latency": ("write_pressure_to_read_latency", "storage_to_replication_delay"),
        "hotspot_or_leader_skew": ("hotspot_to_queue_and_latency",),
    }
    chain_names = mapping.get(category, ())
    confidence = max((chain.confidence for chain in causal_chains if chain.name in chain_names), default=0.0)
    if confidence >= 0.75:
        return 0.10
    if confidence >= 0.50:
        return 0.06
    if confidence > 0:
        return 0.03
    return 0.0


def build_log_score_map(log_events: list[LogEvent]) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    severity_score = {"info": 0.25, "warning": 0.55, "critical": 0.85}
    for event in log_events:
        score = severity_score.get(event.severity, 0.35)
        scores[event.rule] = max(scores[event.rule], score)
        for category in event.categories:
            scores[f"log_{category}_warnings"] = max(scores[f"log_{category}_warnings"], score)
    return dict(scores)


def confidence_band(config: dict[str, Any], score: float) -> str:
    scoring = config.get("scoring", {})
    if score >= float(scoring.get("confidence_high", 0.8)):
        return "high"
    if score >= float(scoring.get("confidence_medium", 0.6)):
        return "medium"
    if score >= float(scoring.get("confidence_low", 0.4)):
        return "low"
    return "insufficient_evidence"
