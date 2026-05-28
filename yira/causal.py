from __future__ import annotations

from collections import defaultdict

from .models import CausalChain, CausalEdge, Signal, TimeWindow


CAUSAL_PATTERNS: dict[str, list[str]] = {
    "write_pressure_to_read_latency": [
        "ysql_ops",
        "wal_pressure",
        "wal_latency",
        "consensus_latency",
        "follower_lag_spike",
        "safe_time_lag",
        "ysql_read_latency",
    ],
    "rpc_queue_to_read_latency": [
        "rpc_queue_size",
        "reactor_delay",
        "rpc_timeout_rate",
        "ysql_read_latency",
    ],
    "storage_to_replication_delay": [
        "iowait",
        "storage_pressure",
        "wal_latency",
        "consensus_latency",
        "follower_lag_spike",
        "ysql_read_latency",
    ],
    "network_to_raft_delay": [
        "network_errors",
        "network_skew",
        "consensus_latency",
        "leader_changes",
        "follower_lag_spike",
        "ysql_read_latency",
    ],
    "master_lookup_to_ysql_latency": [
        "catalog_cache_miss",
        "tablet_location_lookup",
        "master_latency",
        "ysql_read_latency",
    ],
    "docdb_read_path_to_ysql_latency": [
        "cache_miss",
        "sstable_pressure",
        "lsm_seek_pressure",
        "docdb_seek_latency",
        "docdb_get_latency",
        "docdb_read_latency",
        "ysql_read_latency",
    ],
    "transaction_contention_to_latency": [
        "txn_conflicts",
        "transaction_contention",
        "docdb_read_latency",
        "ysql_read_latency",
    ],
    "hotspot_to_queue_and_latency": [
        "hotspot_or_tablet_skew",
        "node_skew",
        "rpc_queue_size",
        "consensus_latency",
        "ysql_read_latency",
    ],
}


def build_causal_chains(
    signals: list[Signal],
    window: TimeWindow,
    max_lag_seconds: int | None = None,
) -> list[CausalChain]:
    if max_lag_seconds is None:
        max_lag_seconds = max(int((window.incident_end - window.incident_start).total_seconds()), 300)
    edges = build_causal_edges(signals, max_lag_seconds)
    chains: list[CausalChain] = []
    for name, pattern in CAUSAL_PATTERNS.items():
        chain_edges = [
            edge
            for edge in edges
            if edge.source_category in pattern and edge.target_category in pattern
            and pattern.index(edge.source_category) < pattern.index(edge.target_category)
        ]
        if not chain_edges:
            continue
        ordered_edges = sorted(chain_edges, key=lambda edge: (pattern.index(edge.source_category), edge.lag_seconds))
        signal_names = ordered_signal_names(ordered_edges)
        confidence = min(sum(edge.confidence for edge in ordered_edges) / max(len(pattern) - 1, 1), 1.0)
        if len(ordered_edges) >= 2:
            confidence = min(confidence + 0.10, 1.0)
        chains.append(
            CausalChain(
                name=name,
                confidence=confidence,
                signals=signal_names,
                edges=ordered_edges[:8],
                explanation=explain_chain(name, ordered_edges),
            )
        )
    return sorted(chains, key=lambda item: (-item.confidence, item.name))


def build_causal_edges(signals: list[Signal], max_lag_seconds: int) -> list[CausalEdge]:
    by_category: dict[str, list[Signal]] = defaultdict(list)
    for signal in signals:
        for category in signal.categories or [signal.category]:
            by_category[category].append(signal)

    edges: list[CausalEdge] = []
    for pattern in CAUSAL_PATTERNS.values():
        for source_category, target_category in zip(pattern, pattern[1:]):
            for source in by_category.get(source_category, []):
                for target in by_category.get(target_category, []):
                    edge = maybe_edge(source, target, source_category, target_category, max_lag_seconds)
                    if edge:
                        edges.append(edge)
    return dedupe_edges(edges)


def maybe_edge(
    source: Signal,
    target: Signal,
    source_category: str,
    target_category: str,
    max_lag_seconds: int,
) -> CausalEdge | None:
    if not source.first_seen or not target.first_seen:
        return None
    lag_seconds = int((target.first_seen - source.first_seen).total_seconds())
    if lag_seconds < 0 or lag_seconds > max_lag_seconds:
        return None
    entity_score = entity_overlap(source, target)
    if entity_score <= 0:
        return None
    lag_score = 1.0 - min(lag_seconds / max(max_lag_seconds, 1), 1.0)
    duration_score = min((source.duration_seconds + target.duration_seconds) / max(max_lag_seconds, 1), 1.0)
    confidence = min((source.score * 0.35) + (target.score * 0.35) + (entity_score * 0.20) + (lag_score * 0.07) + (duration_score * 0.03), 1.0)
    return CausalEdge(
        source=source.name,
        target=target.name,
        source_category=source_category,
        target_category=target_category,
        lag_seconds=lag_seconds,
        confidence=confidence,
        reason=f"{source.name} preceded {target.name} by {lag_seconds}s with entity overlap {entity_score:.2f}",
    )


def entity_overlap(source: Signal, target: Signal) -> float:
    source_nodes = set(source.affected_nodes)
    target_nodes = set(target.affected_nodes)
    if source_nodes and target_nodes and source_nodes & target_nodes:
        return 1.0
    source_regions = set(source.affected_regions)
    target_regions = set(target.affected_regions)
    if source_regions and target_regions and source_regions & target_regions:
        return 0.75
    if not source_nodes and not target_nodes and not source_regions and not target_regions:
        return 0.50
    return 0.25


def ordered_signal_names(edges: list[CausalEdge]) -> list[str]:
    names: list[str] = []
    for edge in edges:
        if edge.source not in names:
            names.append(edge.source)
        if edge.target not in names:
            names.append(edge.target)
    return names


def explain_chain(name: str, edges: list[CausalEdge]) -> str:
    if not edges:
        return name
    pieces = [edges[0].source]
    pieces.extend(edge.target for edge in edges)
    return " -> ".join(pieces)


def dedupe_edges(edges: list[CausalEdge]) -> list[CausalEdge]:
    by_pair: dict[tuple[str, str, str, str], CausalEdge] = {}
    for edge in edges:
        key = (edge.source, edge.target, edge.source_category, edge.target_category)
        existing = by_pair.get(key)
        if existing is None or edge.confidence > existing.confidence:
            by_pair[key] = edge
    return sorted(by_pair.values(), key=lambda item: (-item.confidence, item.lag_seconds))
