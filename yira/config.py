from __future__ import annotations

import os
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from string import Template
from typing import Any

import yaml

from .metric_catalog import YBA_UI_METRICS
from .models import TimeWindow


DEFAULT_CONFIG: dict[str, Any] = {
    "app": {"name": "yira", "environment": "prod", "timezone": "UTC"},
    "window": {
        "step": "30s",
        "rate_window": "2m",
        "baseline": {"before": "30m"},
        "recovery": {"after": "15m"},
    },
    "topology": {
        "expected_node_count": None,
        "regions": [],
        "node_label_mapping": {
            "node": "exported_instance",
            "region": "region",
            "az": "az",
        },
    },
    "data_sources": {
        "prometheus": {
            "enabled": True,
            "collect_mode": "configured_and_discovered",
            "timeout": "30s",
            "retries": 3,
            "max_concurrency": 4,
            "discovery": {
                "enabled": True,
                "max_metrics": 2000,
                "include_regex": "",
                "exclude_regex": "(?i)(ycql|cql|cassandra|redis)",
            },
        },
        "logs": {"enabled": False, "path": "./logs"},
    },
    "detection": {
        "min_duration": "60s",
        "zscore_warning": 2.5,
        "zscore_critical": 4.0,
        "default_warning_multiplier": 3.0,
        "default_critical_multiplier": 10.0,
        "skew": {
            "warning_ratio": 3.0,
            "critical_ratio": 8.0,
        },
    },
    "scoring": {
        "confidence_high": 0.80,
        "confidence_medium": 0.60,
        "confidence_low": 0.40,
    },
    "output": {
        "directory": "./reports",
        "formats": ["markdown", "json"],
        "include_promql": True,
        "include_raw_samples": False,
    },
    "metrics": {},
    "root_causes": {},
    "logs": {"patterns": {}},
}


DEFAULT_METRICS: dict[str, Any] = {
    "ysql_select_latency_p99": {
        "unit": "ms",
        "query": 'histogram_quantile(0.99, sum by (le, exported_instance, region) (rate(handler_latency_yb_ysqlserver_SQLProcessor_SelectStmt_bucket{${metric_filter}}[$rate_window]))) / 1000',
        "required": False,
        "categories": ["ysql_read_latency", "latency"],
        "severity": {"warning": {"gt": 500}, "critical": {"gt": 5000}},
    },
    "consensus_update_latency_p99": {
        "unit": "ms",
        "query": 'histogram_quantile(0.99, sum by (le, exported_instance, region) (rate(handler_latency_yb_consensus_ConsensusService_UpdateConsensus_bucket{${metric_filter}}[$rate_window]))) / 1000',
        "required": False,
        "categories": ["consensus_latency", "replication"],
        "severity": {"warning": {"gt": 250}, "critical": {"gt": 1000}},
    },
    "rpc_queue_size": {
        "unit": "count",
        "query": 'sum by (exported_instance, region, service_type, service_method) (rpcs_in_queue{${metric_filter}})',
        "required": False,
        "categories": ["rpc_queue_size", "rpc"],
        "severity": {"warning": {"gt": 5}, "critical": {"gt": 20}},
    },
    "rpc_queue_overflow_rate": {
        "unit": "events_per_sec",
        "query": 'sum by (exported_instance, region, service_type, service_method) (rate(rpcs_queue_overflow{${metric_filter}}[$rate_window]))',
        "required": False,
        "categories": ["rpc_overflow_rate", "rpc"],
        "severity": {"warning": {"gt": 0}, "critical": {"gt": 1}},
    },
    "rpc_timeout_rate": {
        "unit": "events_per_sec",
        "query": 'sum by (exported_instance, region, service_type, service_method) (rate(rpcs_timed_out_in_queue{${metric_filter}}[$rate_window]))',
        "required": False,
        "categories": ["rpc_timeout_rate", "rpc"],
        "severity": {"warning": {"gt": 0}, "critical": {"gt": 1}},
    },
    "follower_lag_ms": {
        "unit": "ms",
        "query": 'max by (exported_instance, region) (follower_lag_ms{${metric_filter}})',
        "required": False,
        "categories": ["follower_lag_spike", "replication"],
        "severity": {"warning": {"gt": 1000}, "critical": {"gt": 5000}},
    },
    "clock_skew_ms": {
        "unit": "ms",
        "query": 'max by (exported_instance, region) (hybrid_clock_skew{${metric_filter}} / 1000)',
        "required": False,
        "categories": ["clock_skew", "clock"],
        "severity": {"warning": {"gt": 250}, "critical": {"gt": 500}},
    },
}
DEFAULT_METRICS = {**YBA_UI_METRICS, **DEFAULT_METRICS}


DEFAULT_ROOT_CAUSES: dict[str, Any] = {
    "replication_delay": {
        "threshold": 0.70,
        "weights": {
            "follower_lag_spike": 0.35,
            "consensus_latency": 0.20,
            "consensus_ops": 0.10,
            "leader_changes": 0.10,
            "remote_bootstrap": 0.10,
            "ysql_read_latency": 0.15,
            "safe_time_lag": 0.10,
            "consistency_wait": 0.10,
            "log_raft_warnings": 0.10,
        },
        "recommendations": [
            "Inspect affected tablets and leader distribution.",
            "Check whether read latency aligns with Raft replication lag.",
        ],
    },
    "rpc_saturation": {
        "threshold": 0.70,
        "weights": {
            "rpc_queue_size": 0.25,
            "rpc_timeout_rate": 0.20,
            "rpc_overflow_rate": 0.20,
            "reactor_delay": 0.15,
            "thread_pressure": 0.10,
            "ysql_read_latency": 0.10,
            "log_deadline_expired": 0.15,
        },
        "recommendations": [
            "Review TServer RPC queues, queue overflow, and timeout counters.",
            "Check workload concurrency and TServer thread pool saturation.",
        ],
    },
    "network_instability": {
        "threshold": 0.70,
        "weights": {
            "tcp_retransmits": 0.20,
            "packet_drops": 0.15,
            "network_errors": 0.20,
            "network_throughput": 0.10,
            "consensus_latency": 0.20,
            "clock_skew": 0.10,
            "region_specific_impact": 0.05,
        },
        "recommendations": [
            "Inspect cross-region network telemetry and packet retransmits.",
            "Check whether Raft latency is region-specific.",
        ],
    },
    "workload_pressure": {
        "threshold": 0.65,
        "weights": {
            "spark_write_throughput": 0.25,
            "tserver_ops": 0.15,
            "ysql_ops": 0.10,
            "rpc_queue_size": 0.15,
            "consensus_latency": 0.15,
            "follower_lag_spike": 0.15,
            "wal_pressure": 0.10,
            "ysql_read_latency": 0.15,
        },
        "recommendations": [
            "Validate Spark batch size, write concurrency, and schedule overlap.",
            "Compare write throughput to Raft/RPC pressure during the incident.",
        ],
    },
    "storage_bottleneck": {
        "threshold": 0.70,
        "weights": {
            "storage_pressure": 0.20,
            "iowait": 0.12,
            "disk_iops": 0.08,
            "disk_bytes": 0.08,
            "wal_latency": 0.10,
            "wal_pressure": 0.08,
            "rocksdb_stalls": 0.10,
            "compaction_pressure": 0.08,
            "flush_pressure": 0.06,
            "docdb_read_latency": 0.06,
            "docdb_write_latency": 0.04,
        },
        "recommendations": [
            "Check node iowait, disk throughput, WAL latency, compaction, flush, and RocksDB stalls.",
            "Compare affected nodes against table or tablet skew and recent write bursts.",
        ],
    },
    "master_pressure": {
        "threshold": 0.65,
        "weights": {
            "master_pressure": 0.20,
            "master_latency": 0.15,
            "catalog_cache_miss": 0.15,
            "tablet_location_lookup": 0.12,
            "master_rpc": 0.10,
            "master_tsservice_read": 0.08,
            "master_tsservice_write": 0.08,
            "master_consensus": 0.07,
            "ddl_activity": 0.05,
            "heartbeat": 0.05,
        },
        "recommendations": [
            "Check master RPC latency, catalog cache misses, GetTabletLocations, and TS heartbeats.",
            "Look for DDL, catalog access, or tablet-location lookup bursts during the incident.",
        ],
    },
    "transaction_contention": {
        "threshold": 0.65,
        "weights": {
            "transaction_contention": 0.30,
            "txn_conflicts": 0.25,
            "txn_expired": 0.10,
            "ysql_read_latency": 0.15,
            "docdb_read_latency": 0.10,
            "log_deadline_expired": 0.10,
        },
        "recommendations": [
            "Inspect transaction conflicts, lock waits, read restarts, and application retry behavior.",
            "Collect pg_locks and pg_stat_activity snapshots if contention remains suspected.",
        ],
    },
    "cpu_or_thread_pressure": {
        "threshold": 0.65,
        "weights": {
            "cpu_pressure": 0.30,
            "thread_pressure": 0.25,
            "resource_pressure": 0.20,
            "reactor_delay": 0.10,
            "context_switch_pressure": 0.10,
            "rpc_queue_size": 0.05,
        },
        "recommendations": [
            "Compare CPU/load/thread pressure on affected nodes with RPC queue growth and query latency.",
            "Check process-level CPU and thread pools for TServer and Master.",
        ],
    },
    "memory_or_cache_pressure": {
        "threshold": 0.65,
        "weights": {
            "memory_pressure": 0.30,
            "tcmalloc_pressure": 0.20,
            "cache_pressure": 0.20,
            "cache_miss": 0.15,
            "sstable_pressure": 0.10,
            "bloom_filter": 0.05,
        },
        "recommendations": [
            "Inspect TCMalloc, block cache usage, cache miss rate, SSTable count, and memory availability.",
            "Check whether read latency aligns with block cache misses or high SSTable fanout.",
        ],
    },
    "docdb_read_path_pressure": {
        "threshold": 0.65,
        "weights": {
            "docdb_read_latency": 0.25,
            "docdb_get_latency": 0.20,
            "docdb_seek_latency": 0.20,
            "docdb_mutex_wait": 0.15,
            "lsm_seek_pressure": 0.10,
            "sstable_pressure": 0.10,
        },
        "recommendations": [
            "Inspect LSM seek/get latency, mutex wait latency, SSTable count, and cache hit/miss behavior.",
            "Check for range scans, cache misses, compaction overlap, or hot tablets.",
        ],
    },
    "raft_or_leader_instability": {
        "threshold": 0.65,
        "weights": {
            "leader_changes": 0.25,
            "consensus_ops": 0.15,
            "consensus_latency": 0.20,
            "remote_bootstrap": 0.15,
            "master_consensus": 0.10,
            "clock_skew": 0.10,
            "network_errors": 0.05,
        },
        "recommendations": [
            "Check leader stepdowns/elections, remote bootstraps, clock skew, and cross-region network health.",
            "Validate that leader placement is stable across the 4+4+2 topology.",
        ],
    },
    "consistency_wait_latency": {
        "threshold": 0.65,
        "weights": {
            "safe_time_lag": 0.30,
            "consistency_wait": 0.25,
            "read_restarts": 0.20,
            "clock_skew": 0.10,
            "follower_lag_spike": 0.10,
            "ysql_read_latency": 0.05,
        },
        "recommendations": [
            "Check safe-time lag, read restarts, follower lag, and hybrid clock skew during the latency window.",
            "Validate whether reads are waiting on consistency rather than SQL execution.",
        ],
    },
    "hotspot_or_leader_skew": {
        "threshold": 0.65,
        "weights": {
            "hotspot_or_tablet_skew": 0.30,
            "leader_skew": 0.20,
            "node_skew": 0.15,
            "tserver_ops": 0.10,
            "rpc_queue_size": 0.10,
            "consensus_latency": 0.10,
            "ysql_read_latency": 0.05,
        },
        "recommendations": [
            "Inspect table/tablet distribution, leader placement, and per-node outliers.",
            "Look for one node, region, table, or tablet carrying disproportionate read/write load.",
        ],
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    config = deep_merge(DEFAULT_CONFIG, loaded)
    config["metrics"] = deep_merge(DEFAULT_METRICS, config.get("metrics", {}))
    config["root_causes"] = deep_merge(DEFAULT_ROOT_CAUSES, config.get("root_causes", {}))
    return expand_env(config)


def expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    if isinstance(value, str):
        return os.path.expandvars(value)
    return value


def require_config(config: dict[str, Any], dotted_key: str) -> Any:
    current: Any = config
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"Missing required config key: {dotted_key}")
        current = current[part]
    return current


def parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_duration(value: str | int | float) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([smhd])\s*", value)
    if not match:
        raise ValueError(f"Invalid duration: {value!r}")
    amount = float(match.group(1))
    unit = match.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return int(amount * multipliers[unit])


def build_window(config: dict[str, Any]) -> TimeWindow:
    start = parse_datetime(require_config(config, "window.incident_start"))
    end = parse_datetime(require_config(config, "window.incident_end"))
    if end <= start:
        raise ValueError("window.incident_end must be after window.incident_start")
    baseline_seconds = parse_duration(config["window"].get("baseline", {}).get("before", "30m"))
    recovery_seconds = parse_duration(config["window"].get("recovery", {}).get("after", "15m"))
    step_seconds = parse_duration(config["window"].get("step", "30s"))
    return TimeWindow(
        incident_start=start,
        incident_end=end,
        query_start=start - timedelta(seconds=baseline_seconds),
        query_end=end + timedelta(seconds=recovery_seconds),
        step_seconds=step_seconds,
        rate_window=config["window"].get("rate_window", "2m"),
    )


def render_template(template: str, config: dict[str, Any], window: TimeWindow) -> str:
    labels = config.get("cluster", {}).get("labels", {})
    universe = labels.get("universe") or config.get("cluster", {}).get("universe_name", "")
    metric_filter = config.get("cluster", {}).get("metric_filter")
    if not metric_filter:
        metric_filter = f'node_prefix="{universe}"' if universe else ""
    else:
        metric_filter = Template(metric_filter).safe_substitute({"universe": universe, **labels})
    values = {
        "universe": universe,
        "metric_filter": metric_filter,
        "rate_window": window.rate_window,
    }
    values.update(labels)
    return Template(template).safe_substitute(values)
