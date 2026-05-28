from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .causal import build_causal_chains
from .config import build_window
from .logs import collect_log_events
from .models import AnalysisReport, MetricSeries, Signal
from .prometheus import collect_prometheus_metrics
from .rca import score_root_causes
from .signals import detect_signals


def analyze(config: dict[str, Any]) -> AnalysisReport:
    window = build_window(config)
    series, missing_metrics = collect_prometheus_metrics(config, window)
    signals = detect_signals(config, window, series)
    causal_chains = build_causal_chains(signals, window)
    log_events = collect_log_events(config, window)
    root_causes = score_root_causes(config, signals, log_events, causal_chains)
    affected_nodes = sorted({node for signal in signals for node in signal.affected_nodes})
    affected_regions = sorted({region for signal in signals for region in signal.affected_regions})
    recommendations = dedupe(
        [
            item
            for cause in root_causes[:3]
            for item in cause.recommendations
        ]
        + topology_recommendations(config, affected_regions)
    )

    return AnalysisReport(
        incident_id=incident_id(config, window.incident_start),
        generated_at=datetime.now(tz=timezone.utc),
        window=window,
        symptom=build_symptom(signals, series),
        root_causes=root_causes,
        signals=signals,
        causal_chains=causal_chains,
        log_events=log_events,
        missing_metrics=missing_metrics,
        affected_nodes=affected_nodes,
        affected_regions=affected_regions,
        recommendations=recommendations,
    )


def build_symptom(signals: list[Signal], series: list[MetricSeries]) -> dict[str, Any]:
    for preferred in ("ysql_select_latency_p99", "api_read_latency_p99"):
        signal = next((item for item in signals if item.name == preferred), None)
        if signal:
            return {
                "name": signal.name,
                "peak": signal.peak,
                "baseline": signal.baseline,
                "unit": signal.unit,
            }
    if signals:
        signal = signals[0]
        return {
            "name": signal.name,
            "peak": signal.peak,
            "baseline": signal.baseline,
            "unit": signal.unit,
        }
    metric_names = sorted({item.metric for item in series})
    return {"name": "undetected", "available_metrics": metric_names}


def incident_id(config: dict[str, Any], start: datetime) -> str:
    universe = config.get("cluster", {}).get("universe_name", "unknown-universe")
    return f"{start.strftime('%Y%m%dT%H%M%SZ')}-{universe}"


def topology_recommendations(config: dict[str, Any], affected_regions: list[str]) -> list[str]:
    topology = config.get("topology", {})
    recommendations: list[str] = []
    regions = topology.get("regions", [])
    small_regions = [
        item.get("name")
        for item in regions
        if item.get("expected_nodes") and int(item["expected_nodes"]) <= 2
    ]
    if set(small_regions) & set(affected_regions):
        recommendations.append(
            "The affected set includes a small region; compare region-normalized load for the 4+4+2 placement."
        )
    if topology.get("leader_preference", {}).get("enabled"):
        recommendations.append("Check whether leader placement matches configured preferred regions.")
    return recommendations


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
