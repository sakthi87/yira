from __future__ import annotations

import statistics
from datetime import datetime
from typing import Any

from .models import MetricSeries, SEVERITY_RANK, Signal, TimeWindow


def detect_signals(
    config: dict[str, Any],
    window: TimeWindow,
    series: list[MetricSeries],
) -> list[Signal]:
    signals: list[Signal] = []
    for metric_name, metric_def in config.get("metrics", {}).items():
        metric_series = [item for item in series if item.metric == metric_name]
        if not metric_series:
            continue
        signal = detect_metric_signal(config, window, metric_name, metric_def, metric_series)
        if signal and signal.severity != "normal":
            signals.append(signal)
        skew_signal = detect_skew_signal(config, window, metric_name, metric_def, metric_series)
        if skew_signal:
            signals.append(skew_signal)
    return sorted(signals, key=lambda item: (-item.score, item.name))


def detect_metric_signal(
    config: dict[str, Any],
    window: TimeWindow,
    metric_name: str,
    metric_def: dict[str, Any],
    metric_series: list[MetricSeries],
) -> Signal | None:
    baseline_values: list[float] = []
    incident_points: list[tuple[datetime, float, MetricSeries]] = []

    for item in metric_series:
        for point in item.points:
            if window.query_start <= point.timestamp < window.incident_start:
                baseline_values.append(point.value)
            elif window.incident_start <= point.timestamp <= window.incident_end:
                incident_points.append((point.timestamp, point.value, item))

    if not incident_points:
        return None

    peak_time, peak_value, peak_series = max(incident_points, key=lambda row: row[1])
    incident_values = [value for _, value, _ in incident_points]
    baseline = statistics.median(baseline_values) if baseline_values else None
    baseline_stdev = statistics.pstdev(baseline_values) if len(baseline_values) > 1 else 0.0
    multiplier = None
    if baseline and baseline > 0:
        multiplier = peak_value / baseline

    severity, reason = threshold_severity(metric_def.get("severity", {}), peak_value)
    zscore = None
    if baseline is not None and baseline_stdev > 0:
        zscore = (peak_value - baseline) / baseline_stdev
        detection = config.get("detection", {})
        if zscore >= float(detection.get("zscore_critical", 4.0)):
            severity = max_severity(severity, "critical")
            reason = append_reason(reason, f"zscore={zscore:.2f}")
        elif zscore >= float(detection.get("zscore_warning", 2.5)):
            severity = max_severity(severity, "warning")
            reason = append_reason(reason, f"zscore={zscore:.2f}")

    if multiplier is not None:
        detection = config.get("detection", {})
        if multiplier >= float(detection.get("default_critical_multiplier", 10.0)):
            severity = max_severity(severity, "critical")
            reason = append_reason(reason, f"{multiplier:.1f}x baseline")
        elif multiplier >= float(detection.get("default_warning_multiplier", 3.0)):
            severity = max_severity(severity, "warning")
            reason = append_reason(reason, f"{multiplier:.1f}x baseline")

    if severity == "normal":
        return Signal(
            name=metric_name,
            metric=metric_name,
            category=primary_category(metric_def, metric_name),
            severity=severity,
            score=0.0,
            peak=peak_value,
            baseline=baseline,
            multiplier=multiplier,
            first_seen=None,
            last_seen=None,
            unit=metric_def.get("unit", ""),
            categories=categories(metric_def, metric_name),
        )

    active_times = [
        timestamp
        for timestamp, value, _ in incident_points
        if threshold_active(metric_def.get("severity", {}), value)
    ]
    score = severity_score(severity, peak_value, incident_values, baseline, zscore, multiplier)
    node_label = config.get("topology", {}).get("node_label_mapping", {}).get("node", "exported_instance")
    region_label = config.get("topology", {}).get("node_label_mapping", {}).get("region", "region")

    return Signal(
        name=metric_name,
        metric=metric_name,
        category=primary_category(metric_def, metric_name),
        severity=severity,
        score=score,
        peak=peak_value,
        baseline=baseline,
        multiplier=multiplier,
        first_seen=min(active_times) if active_times else peak_time,
        last_seen=max(active_times) if active_times else peak_time,
        unit=metric_def.get("unit", ""),
        categories=categories(metric_def, metric_name),
        affected_nodes=label_values(metric_series, node_label),
        affected_regions=label_values(metric_series, region_label),
        labels=peak_series.labels,
        reason=reason or f"peak={peak_value:.2f}{metric_def.get('unit', '')}",
    )


def detect_skew_signal(
    config: dict[str, Any],
    window: TimeWindow,
    metric_name: str,
    metric_def: dict[str, Any],
    metric_series: list[MetricSeries],
) -> Signal | None:
    node_label = config.get("topology", {}).get("node_label_mapping", {}).get("node", "exported_instance")
    region_label = config.get("topology", {}).get("node_label_mapping", {}).get("region", "region")
    peaks: list[tuple[str, str, float, datetime, MetricSeries]] = []
    for item in metric_series:
        node = item.labels.get(node_label)
        if not node:
            continue
        incident_points = [
            point
            for point in item.points
            if window.incident_start <= point.timestamp <= window.incident_end
        ]
        if not incident_points:
            continue
        peak = max(incident_points, key=lambda point: point.value)
        peaks.append((node, item.labels.get(region_label, ""), peak.value, peak.timestamp, item))

    if len(peaks) < 3:
        return None
    values = [value for _, _, value, _, _ in peaks]
    median_value = statistics.median(values)
    if median_value <= 0:
        return None
    node, region, peak_value, peak_time, peak_series = max(peaks, key=lambda row: row[2])
    ratio = peak_value / median_value
    skew_config = config.get("detection", {}).get("skew", {})
    warning_ratio = float(skew_config.get("warning_ratio", 3.0))
    critical_ratio = float(skew_config.get("critical_ratio", 8.0))
    if ratio < warning_ratio:
        return None

    severity = "critical" if ratio >= critical_ratio else "warning"
    score = min(0.55 + (ratio / 20), 0.95)
    metric_categories = categories(metric_def, metric_name)
    skew_category = infer_skew_category(metric_categories)
    return Signal(
        name=f"{metric_name}_node_skew",
        metric=metric_name,
        category=skew_category,
        severity=severity,
        score=score,
        peak=peak_value,
        baseline=median_value,
        multiplier=ratio,
        first_seen=peak_time,
        last_seen=peak_time,
        unit=metric_def.get("unit", ""),
        categories=[skew_category, "node_skew"] + metric_categories,
        affected_nodes=[node],
        affected_regions=[region] if region else [],
        labels=peak_series.labels,
        reason=f"node {node} is {ratio:.1f}x cluster median for {metric_name}",
    )


def threshold_severity(thresholds: dict[str, Any], value: float) -> tuple[str, str]:
    severity = "normal"
    reason = ""
    for candidate in ("warning", "critical"):
        rule = thresholds.get(candidate, {})
        gt = rule.get("gt")
        if gt is not None and value > float(gt):
            severity = candidate
            reason = append_reason(reason, f"value {value:.2f} > {gt}")
        lt = rule.get("lt")
        if lt is not None and value < float(lt):
            severity = candidate
            reason = append_reason(reason, f"value {value:.2f} < {lt}")
    return severity, reason


def warning_threshold(thresholds: dict[str, Any]) -> float | None:
    rule = thresholds.get("warning") or thresholds.get("critical") or {}
    gt = rule.get("gt")
    if gt is not None:
        return float(gt)
    lt = rule.get("lt")
    return float(lt) if lt is not None else None


def threshold_active(thresholds: dict[str, Any], value: float) -> bool:
    rule = thresholds.get("warning") or thresholds.get("critical") or {}
    gt = rule.get("gt")
    if gt is not None:
        return value >= float(gt)
    lt = rule.get("lt")
    if lt is not None:
        return value <= float(lt)
    return True


def severity_score(
    severity: str,
    peak: float,
    incident_values: list[float],
    baseline: float | None,
    zscore: float | None,
    multiplier: float | None,
) -> float:
    base = {"normal": 0.0, "info": 0.2, "warning": 0.55, "critical": 0.85}[severity]
    if baseline is not None and peak > baseline:
        base += min((peak - baseline) / max(abs(peak), 1.0), 0.10)
    if zscore is not None:
        base += min(zscore / 100, 0.05)
    if multiplier is not None:
        base += min(multiplier / 100, 0.05)
    if incident_values and peak == max(incident_values):
        base += 0.02
    return min(base, 1.0)


def primary_category(metric_def: dict[str, Any], fallback: str) -> str:
    metric_categories = categories(metric_def, fallback)
    return metric_categories[0] if metric_categories else fallback


def categories(metric_def: dict[str, Any], fallback: str) -> list[str]:
    metric_categories = metric_def.get("categories") or []
    return list(metric_categories) if metric_categories else [fallback]


def infer_skew_category(metric_categories: list[str]) -> str:
    if any(item in metric_categories for item in ("tserver_ops", "ysql_ops", "docdb_write_latency")):
        return "hotspot_or_tablet_skew"
    if any(item in metric_categories for item in ("leader_changes", "consensus_latency", "consensus_ops")):
        return "leader_skew"
    if any(item in metric_categories for item in ("network", "network_errors", "network_throughput")):
        return "network_skew"
    if any(item in metric_categories for item in ("storage_pressure", "iowait", "disk_iops")):
        return "storage_skew"
    return "node_skew"


def max_severity(left: str, right: str) -> str:
    return left if SEVERITY_RANK[left] >= SEVERITY_RANK[right] else right


def append_reason(existing: str, addition: str) -> str:
    return f"{existing}; {addition}" if existing else addition


def label_values(series: list[MetricSeries], label: str) -> list[str]:
    values = sorted({item.labels[label] for item in series if item.labels.get(label)})
    return values
