from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import LogEvent, RootCauseScore, Signal


def score_root_causes(
    config: dict[str, Any],
    signals: list[Signal],
    log_events: list[LogEvent],
) -> list[RootCauseScore]:
    signal_scores = build_signal_score_map(signals)
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
        names = {signal.name, signal.category}
        for label in signal.labels.values():
            if label:
                names.add(label)
        for name in names:
            scores[name] = max(scores[name], signal.score)
    return dict(scores)


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
