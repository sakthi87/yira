from __future__ import annotations

from datetime import datetime, timedelta, timezone

from yira.causal import build_causal_chains
from yira.config import DEFAULT_CONFIG, build_window, deep_merge
from yira.metric_catalog import YBA_UI_METRICS, is_ycql_metric
from yira.models import LogEvent, MetricPoint, MetricSeries, Signal, TimeWindow
from yira.rca import score_root_causes
from yira.signals import detect_signals


def test_window_expansion() -> None:
    config = deep_merge(
        DEFAULT_CONFIG,
        {
            "window": {
                "incident_start": "2026-05-26T10:00:00Z",
                "incident_end": "2026-05-26T10:30:00Z",
                "baseline": {"before": "30m"},
                "recovery": {"after": "15m"},
                "step": "30s",
            }
        },
    )
    window = build_window(config)
    assert window.query_start.isoformat() == "2026-05-26T09:30:00+00:00"
    assert window.query_end.isoformat() == "2026-05-26T10:45:00+00:00"
    assert window.step_seconds == 30


def test_yba_catalog_explicitly_excludes_ycql_metrics() -> None:
    assert len(YBA_UI_METRICS) >= 70
    assert not any(is_ycql_metric(name) for name in YBA_UI_METRICS)
    assert "docdb_get_latency_ms" in YBA_UI_METRICS
    assert "master_get_tablet_locations_rate" in YBA_UI_METRICS
    assert "node_network_packets" in YBA_UI_METRICS


def test_detects_threshold_and_baseline_signal() -> None:
    start = datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc)
    config = deep_merge(
        DEFAULT_CONFIG,
        {
            "window": {
                "incident_start": start.isoformat(),
                "incident_end": (start + timedelta(minutes=5)).isoformat(),
            },
            "metrics": {
                "rpc_queue_size": {
                    "unit": "count",
                    "query": "unused",
                    "categories": ["rpc_queue_size", "rpc"],
                    "severity": {"warning": {"gt": 5}, "critical": {"gt": 20}},
                }
            },
        },
    )
    window = build_window(config)
    points = [
        MetricPoint(start - timedelta(minutes=10), 1),
        MetricPoint(start - timedelta(minutes=5), 1),
        MetricPoint(start + timedelta(minutes=1), 42),
    ]
    series = [
        MetricSeries(
            metric="rpc_queue_size",
            labels={"exported_instance": "node-7", "region": "region-c"},
            unit="count",
            query="unused",
            points=points,
        )
    ]
    signals = detect_signals(config, window, series)
    assert len(signals) == 1
    assert signals[0].severity == "critical"
    assert signals[0].affected_nodes == ["node-7"]
    assert signals[0].affected_regions == ["region-c"]


def test_detects_node_skew_signal() -> None:
    start = datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc)
    config = deep_merge(
        DEFAULT_CONFIG,
        {
            "window": {
                "incident_start": start.isoformat(),
                "incident_end": (start + timedelta(minutes=5)).isoformat(),
            },
            "metrics": {
                "tserver_ops": {
                    "unit": "ops_per_sec",
                    "query": "unused",
                    "categories": ["tserver_ops", "workload"],
                    "severity": {},
                }
            },
        },
    )
    window = build_window(config)
    series = [
        MetricSeries("tserver_ops", {"exported_instance": "node-1", "region": "a"}, "ops", "unused", [MetricPoint(start + timedelta(minutes=1), 10)]),
        MetricSeries("tserver_ops", {"exported_instance": "node-2", "region": "a"}, "ops", "unused", [MetricPoint(start + timedelta(minutes=1), 11)]),
        MetricSeries("tserver_ops", {"exported_instance": "node-3", "region": "b"}, "ops", "unused", [MetricPoint(start + timedelta(minutes=1), 100)]),
    ]
    signals = detect_signals(config, window, series)
    assert any(signal.category == "hotspot_or_tablet_skew" for signal in signals)


def test_builds_temporal_causal_chain() -> None:
    start = datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc)
    window = TimeWindow(start, start + timedelta(minutes=10), start - timedelta(minutes=5), start + timedelta(minutes=10), 30, "2m")
    signals = [
        Signal("wal", "wal", "wal_latency", "warning", 0.8, 1, 0, None, start, start + timedelta(minutes=2), "ms", ["wal_latency"], ["node-1"], ["region-a"]),
        Signal("consensus", "consensus", "consensus_latency", "warning", 0.8, 1, 0, None, start + timedelta(minutes=1), start + timedelta(minutes=3), "ms", ["consensus_latency"], ["node-1"], ["region-a"]),
        Signal("lag", "lag", "follower_lag_spike", "warning", 0.8, 1, 0, None, start + timedelta(minutes=2), start + timedelta(minutes=4), "ms", ["follower_lag_spike"], ["node-1"], ["region-a"]),
        Signal("ysql", "ysql", "ysql_read_latency", "critical", 0.9, 1, 0, None, start + timedelta(minutes=3), start + timedelta(minutes=5), "ms", ["ysql_read_latency"], ["node-1"], ["region-a"]),
    ]
    chains = build_causal_chains(signals, window)
    assert any(chain.name == "storage_to_replication_delay" for chain in chains)


def test_scores_root_causes_from_signals_and_logs() -> None:
    start = datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc)
    config = deep_merge(
        DEFAULT_CONFIG,
        {
            "root_causes": {
                "rpc_saturation": {
                    "threshold": 0.7,
                    "weights": {
                        "rpc_queue_size": 0.5,
                        "log_deadline_expired": 0.5,
                    },
                    "recommendations": ["review rpc queues"],
                }
            }
        },
    )
    signal = type(
        "SignalLike",
        (),
        {
            "name": "rpc_queue_size",
            "category": "rpc_queue_size",
            "score": 0.9,
            "labels": {},
        },
    )()
    log_event = LogEvent(
        timestamp=start,
        rule="log_deadline_expired",
        severity="critical",
        categories=["rpc"],
        path="tserver.log",
        line_number=1,
        message="deadline expired",
    )
    scores = score_root_causes(config, [signal], [log_event])  # type: ignore[list-item]
    assert scores[0].category == "rpc_saturation"
    assert scores[0].score >= 0.85
