from __future__ import annotations

import re
from typing import Any


YCQL_EXCLUDE_RE = re.compile(r"(?i)(^|_)(ycql|cql|cassandra)(_|$)|yb_cqlserver")
HISTOGRAM_BUCKET_RE = re.compile(r"(?i)(_bucket$|_created$)")
COUNTER_RE = re.compile(r"(?i)(_total$|_count$|_sum$|ops$|operations$|bytes_(read|written)|messages$)")


YBA_UI_METRICS: dict[str, Any] = {
    # YSQL ops and latency.
    "ysql_ops_rate": {
        "unit": "ops_per_sec",
        "query": 'sum by (exported_instance, region, statement_type) (rate(ysql_server_rpc_performed{${metric_filter}}[$rate_window]))',
        "required": False,
        "categories": ["ysql_ops", "workload"],
        "severity": {"warning": {"gt": 10000}, "critical": {"gt": 25000}},
    },
    "ysql_latency_avg_ms": {
        "unit": "ms",
        "query": '(sum by (exported_instance, region, statement_type) (rate(ysql_server_rpc_latency_sum{${metric_filter}}[$rate_window])) / sum by (exported_instance, region, statement_type) (rate(ysql_server_rpc_latency_count{${metric_filter}}[$rate_window]))) / 1000',
        "required": False,
        "categories": ["ysql_read_latency", "latency"],
        "severity": {"warning": {"gt": 500}, "critical": {"gt": 5000}},
    },
    "ysql_connections": {
        "unit": "connections",
        "query": 'sum by (exported_instance, region) (ysqlserver_rpc_connections_alive{${metric_filter}})',
        "required": False,
        "categories": ["ysql_connections", "resource_pressure"],
        "severity": {"warning": {"gt": 240}, "critical": {"gt": 290}},
    },
    "ysql_catalog_cache_misses": {
        "unit": "events_per_sec",
        "query": 'sum by (exported_instance, region) (rate(ysql_catalog_cache_misses{${metric_filter}}[$rate_window]))',
        "required": False,
        "categories": ["catalog_cache_miss", "master_pressure"],
        "severity": {"warning": {"gt": 1}, "critical": {"gt": 10}},
    },
    # Resource metrics.
    "node_cpu_usage": {
        "unit": "ratio",
        "query": '1 - avg by (exported_instance, region) (rate(node_cpu_seconds_total{${metric_filter},mode="idle"}[$rate_window]))',
        "required": False,
        "categories": ["cpu_pressure", "resource_pressure"],
        "severity": {"warning": {"gt": 0.75}, "critical": {"gt": 0.90}},
    },
    "node_iowait": {
        "unit": "ratio",
        "query": 'avg by (exported_instance, region) (rate(node_cpu_seconds_total{${metric_filter},mode="iowait"}[$rate_window]))',
        "required": False,
        "categories": ["iowait", "storage_pressure"],
        "severity": {"warning": {"gt": 0.15}, "critical": {"gt": 0.25}},
    },
    "node_load1": {
        "unit": "load",
        "query": 'avg by (exported_instance, region) (node_load1{${metric_filter}})',
        "required": False,
        "categories": ["cpu_pressure", "resource_pressure"],
        "severity": {"warning": {"gt": 8}, "critical": {"gt": 16}},
    },
    "node_memory_available_ratio": {
        "unit": "ratio",
        "query": 'avg by (exported_instance, region) (node_memory_MemAvailable_bytes{${metric_filter}} / node_memory_MemTotal_bytes{${metric_filter}})',
        "required": False,
        "categories": ["memory_pressure"],
        "severity": {"warning": {"lt": 0.15}, "critical": {"lt": 0.05}},
    },
    "node_disk_iops": {
        "unit": "ops_per_sec",
        "query": 'sum by (exported_instance, region, device) (rate(node_disk_reads_completed_total{${metric_filter}}[$rate_window]) + rate(node_disk_writes_completed_total{${metric_filter}}[$rate_window]))',
        "required": False,
        "categories": ["disk_iops", "storage_pressure"],
        "severity": {"warning": {"gt": 5000}, "critical": {"gt": 10000}},
    },
    "node_disk_bytes": {
        "unit": "bytes_per_sec",
        "query": 'sum by (exported_instance, region, device) (rate(node_disk_read_bytes_total{${metric_filter}}[$rate_window]) + rate(node_disk_written_bytes_total{${metric_filter}}[$rate_window]))',
        "required": False,
        "categories": ["disk_bytes", "storage_pressure"],
        "severity": {"warning": {"gt": 100000000}, "critical": {"gt": 300000000}},
    },
    "node_network_bytes": {
        "unit": "bytes_per_sec",
        "query": 'sum by (exported_instance, region, device) (rate(node_network_receive_bytes_total{${metric_filter}}[$rate_window]) + rate(node_network_transmit_bytes_total{${metric_filter}}[$rate_window]))',
        "required": False,
        "categories": ["network_throughput", "network"],
        "severity": {"warning": {"gt": 100000000}, "critical": {"gt": 500000000}},
    },
    "node_network_errors": {
        "unit": "errors_per_sec",
        "query": 'sum by (exported_instance, region, device) (rate(node_network_receive_errs_total{${metric_filter}}[$rate_window]) + rate(node_network_transmit_errs_total{${metric_filter}}[$rate_window]))',
        "required": False,
        "categories": ["network_errors", "network"],
        "severity": {"warning": {"gt": 0}, "critical": {"gt": 1}},
    },
    # Tablet server / DocDB / Raft / WAL.
    "tserver_read_latency_avg_ms": {
        "unit": "ms",
        "query": '(sum by (exported_instance, region, table_name) (rate(ql_read_latency_sum{${metric_filter}, namespace_name!="system_platform"}[$rate_window])) / sum by (exported_instance, region, table_name) (rate(ql_read_latency_count{${metric_filter}, namespace_name!="system_platform"}[$rate_window]))) / 1000',
        "required": False,
        "categories": ["docdb_read_latency", "latency"],
        "severity": {"warning": {"gt": 500}, "critical": {"gt": 5000}},
    },
    "tserver_write_latency_avg_ms": {
        "unit": "ms",
        "query": '(sum by (exported_instance, region, table_name) (rate(ql_write_latency_sum{${metric_filter}, namespace_name!="system_platform"}[$rate_window])) / sum by (exported_instance, region, table_name) (rate(ql_write_latency_count{${metric_filter}, namespace_name!="system_platform"}[$rate_window]))) / 1000',
        "required": False,
        "categories": ["docdb_write_latency", "storage_pressure"],
        "severity": {"warning": {"gt": 500}, "critical": {"gt": 5000}},
    },
    "wal_latency_avg_ms": {
        "unit": "ms",
        "query": '(sum by (exported_instance, region) (rate(log_append_latency_sum{${metric_filter}}[$rate_window]) + rate(log_sync_latency_sum{${metric_filter}}[$rate_window])) / sum by (exported_instance, region) (rate(log_append_latency_count{${metric_filter}}[$rate_window]) + rate(log_sync_latency_count{${metric_filter}}[$rate_window]))) / 1000',
        "required": False,
        "categories": ["wal_latency", "storage_pressure"],
        "severity": {"warning": {"gt": 50}, "critical": {"gt": 250}},
    },
    "wal_bytes_written": {
        "unit": "bytes_per_sec",
        "query": 'sum by (exported_instance, region) (rate(log_bytes_logged{${metric_filter}}[$rate_window]))',
        "required": False,
        "categories": ["wal_pressure", "workload"],
        "severity": {"warning": {"gt": 50000000}, "critical": {"gt": 200000000}},
    },
    "wal_cache_size": {
        "unit": "bytes",
        "query": 'sum by (exported_instance, region) (log_cache_size{${metric_filter}})',
        "required": False,
        "categories": ["follower_lag_spike", "replication"],
        "severity": {"warning": {"gt": 1}, "critical": {"gt": 100000000}},
    },
    "rocksdb_stalls": {
        "unit": "micros_per_sec",
        "query": 'sum by (exported_instance, region, table_name) (rate(rocksdb_stall_micros{${metric_filter}}[$rate_window]))',
        "required": False,
        "categories": ["rocksdb_stalls", "storage_pressure"],
        "severity": {"warning": {"gt": 0}, "critical": {"gt": 1000000}},
    },
    "rocksdb_compaction_time": {
        "unit": "micros_per_sec",
        "query": 'sum by (exported_instance, region, table_name) (rate(rocksdb_compact_micros{${metric_filter}}[$rate_window]))',
        "required": False,
        "categories": ["compaction_pressure", "storage_pressure"],
        "severity": {"warning": {"gt": 1000000}, "critical": {"gt": 10000000}},
    },
    "rocksdb_flush_write_bytes": {
        "unit": "bytes_per_sec",
        "query": 'sum by (exported_instance, region, table_name) (rate(rocksdb_flush_write_bytes{${metric_filter}}[$rate_window]))',
        "required": False,
        "categories": ["flush_pressure", "storage_pressure"],
        "severity": {"warning": {"gt": 50000000}, "critical": {"gt": 200000000}},
    },
    "rocksdb_block_cache_miss_rate": {
        "unit": "events_per_sec",
        "query": 'sum by (exported_instance, region, table_name) (rate(rocksdb_block_cache_miss{${metric_filter}}[$rate_window]))',
        "required": False,
        "categories": ["cache_miss", "storage_pressure"],
        "severity": {"warning": {"gt": 1000}, "critical": {"gt": 10000}},
    },
    "txn_conflicts": {
        "unit": "events_per_sec",
        "query": 'sum by (exported_instance, region) (rate(transaction_conflicts{${metric_filter}}[$rate_window]))',
        "required": False,
        "categories": ["txn_conflicts", "transaction_contention"],
        "severity": {"warning": {"gt": 1}, "critical": {"gt": 10}},
    },
    "remote_bootstrap_rate": {
        "unit": "events_per_sec",
        "query": 'sum by (exported_instance, region) (rate(handler_latency_yb_consensus_ConsensusService_StartRemoteBootstrap_count{${metric_filter}}[$rate_window]))',
        "required": False,
        "categories": ["remote_bootstrap", "replication"],
        "severity": {"warning": {"gt": 0}, "critical": {"gt": 1}},
    },
    "leader_changes": {
        "unit": "events_per_sec",
        "query": 'sum by (exported_instance, region) (rate(handler_latency_yb_consensus_ConsensusService_LeaderStepDown_count{${metric_filter}}[$rate_window]) + rate(handler_latency_yb_consensus_ConsensusService_RunLeaderElection_count{${metric_filter}}[$rate_window]))',
        "required": False,
        "categories": ["leader_changes", "replication"],
        "severity": {"warning": {"gt": 0}, "critical": {"gt": 1}},
    },
    # Master server.
    "master_rpc_rate": {
        "unit": "ops_per_sec",
        "query": 'sum by (exported_instance, region) (rate(rpcs_received{${metric_filter}, export_type="master_export"}[$rate_window]))',
        "required": False,
        "categories": ["master_pressure", "master_rpc"],
        "severity": {"warning": {"gt": 500}, "critical": {"gt": 1000}},
    },
    "master_rpc_queue_size": {
        "unit": "count",
        "query": 'sum by (exported_instance, region, service_type, service_method) (rpcs_in_queue{${metric_filter}, export_type="master_export"})',
        "required": False,
        "categories": ["master_pressure", "rpc_queue_size"],
        "severity": {"warning": {"gt": 5}, "critical": {"gt": 20}},
    },
    "master_tserver_heartbeat_rate": {
        "unit": "ops_per_sec",
        "query": 'sum by (exported_instance, region) (rate(handler_latency_yb_master_MasterService_TSHeartbeat_count{${metric_filter}}[$rate_window]))',
        "required": False,
        "categories": ["master_pressure", "heartbeat"],
        "severity": {"warning": {"gt": 1000}, "critical": {"gt": 5000}},
    },
}


YBA_UI_METRICS.update(
    {
        # Resource metrics not covered by the first pass.
        "node_memory_buffered_bytes": {
            "unit": "bytes",
            "query": 'avg by (exported_instance, region) (node_memory_Buffers_bytes{${metric_filter}})',
            "required": False,
            "categories": ["memory_pressure", "resource_pressure"],
            "severity": {},
        },
        "node_memory_cached_bytes": {
            "unit": "bytes",
            "query": 'avg by (exported_instance, region) (node_memory_Cached_bytes{${metric_filter}})',
            "required": False,
            "categories": ["memory_pressure", "resource_pressure"],
            "severity": {},
        },
        "node_memory_free_bytes": {
            "unit": "bytes",
            "query": 'avg by (exported_instance, region) (node_memory_MemFree_bytes{${metric_filter}})',
            "required": False,
            "categories": ["memory_pressure", "resource_pressure"],
            "severity": {},
        },
        "node_network_packets": {
            "unit": "packets_per_sec",
            "query": 'sum by (exported_instance, region, device) (rate(node_network_receive_packets_total{${metric_filter}}[$rate_window]) + rate(node_network_transmit_packets_total{${metric_filter}}[$rate_window]))',
            "required": False,
            "categories": ["network_throughput", "network"],
            "severity": {"warning": {"gt": 100000}, "critical": {"gt": 500000}},
        },
        "node_load5": {
            "unit": "load",
            "query": 'avg by (exported_instance, region) (node_load5{${metric_filter}})',
            "required": False,
            "categories": ["cpu_pressure", "resource_pressure"],
            "severity": {"warning": {"gt": 8}, "critical": {"gt": 16}},
        },
        "node_load15": {
            "unit": "load",
            "query": 'avg by (exported_instance, region) (node_load15{${metric_filter}})',
            "required": False,
            "categories": ["cpu_pressure", "resource_pressure"],
            "severity": {"warning": {"gt": 8}, "critical": {"gt": 16}},
        },
        # Tablet Server metrics.
        "tserver_ops_rate": {
            "unit": "ops_per_sec",
            "query": 'sum by (exported_instance, region, table_name) (rate(ql_read_latency_count{${metric_filter}, namespace_name!="system_platform"}[$rate_window]) + rate(ql_write_latency_count{${metric_filter}, namespace_name!="system_platform"}[$rate_window]))',
            "required": False,
            "categories": ["tserver_ops", "workload"],
            "severity": {"warning": {"gt": 10000}, "critical": {"gt": 25000}},
        },
        "tserver_reactor_delay_ms": {
            "unit": "ms",
            "query": '(sum by (exported_instance, region) (rate(handler_latency_yb_tserver_TabletServerService_Read_sum{${metric_filter}}[$rate_window]) + rate(handler_latency_yb_tserver_TabletServerService_Write_sum{${metric_filter}}[$rate_window])) / sum by (exported_instance, region) (rate(handler_latency_yb_tserver_TabletServerService_Read_count{${metric_filter}}[$rate_window]) + rate(handler_latency_yb_tserver_TabletServerService_Write_count{${metric_filter}}[$rate_window]))) / 1000',
            "required": False,
            "categories": ["reactor_delay", "rpc_queue_size", "network"],
            "severity": {"warning": {"gt": 50}, "critical": {"gt": 250}},
        },
        "tserver_threads_running": {
            "unit": "threads",
            "query": 'sum by (exported_instance, region) (server_threads_running{${metric_filter}, export_type="tserver_export"})',
            "required": False,
            "categories": ["thread_pressure", "resource_pressure"],
            "severity": {"warning": {"gt": 500}, "critical": {"gt": 1000}},
        },
        "tserver_threads_started": {
            "unit": "threads_per_sec",
            "query": 'sum by (exported_instance, region) (rate(server_threads_started{${metric_filter}, export_type="tserver_export"}[$rate_window]))',
            "required": False,
            "categories": ["thread_pressure", "resource_pressure"],
            "severity": {"warning": {"gt": 10}, "critical": {"gt": 100}},
        },
        "tserver_context_switches": {
            "unit": "events_per_sec",
            "query": 'sum by (exported_instance, region) (rate(voluntary_context_switches{${metric_filter}, export_type="tserver_export"}[$rate_window]) + rate(involuntary_context_switches{${metric_filter}, export_type="tserver_export"}[$rate_window]))',
            "required": False,
            "categories": ["context_switch_pressure", "cpu_pressure", "resource_pressure"],
            "severity": {"warning": {"gt": 10000}, "critical": {"gt": 50000}},
        },
        "tserver_spinlock_time": {
            "unit": "microseconds_per_sec",
            "query": 'sum by (exported_instance, region) (rate(spinlock_contention_time{${metric_filter}, export_type="tserver_export"}[$rate_window]))',
            "required": False,
            "categories": ["spinlock_pressure", "cpu_pressure", "resource_pressure"],
            "severity": {"warning": {"gt": 1000000}, "critical": {"gt": 10000000}},
        },
        "consensus_ops_rate": {
            "unit": "ops_per_sec",
            "query": 'sum by (exported_instance, region) (rate(handler_latency_yb_consensus_ConsensusService_UpdateConsensus_count{${metric_filter}}[$rate_window]) + rate(handler_latency_yb_consensus_ConsensusService_RequestConsensusVotes_count{${metric_filter}}[$rate_window]) + rate(handler_latency_yb_consensus_ConsensusService_MultiRaftUpdateConsensus_count{${metric_filter}}[$rate_window]))',
            "required": False,
            "categories": ["consensus_ops", "replication"],
            "severity": {"warning": {"gt": 1000}, "critical": {"gt": 5000}},
        },
        "consensus_change_config_rate": {
            "unit": "events_per_sec",
            "query": 'sum by (exported_instance, region) (rate(handler_latency_yb_consensus_ConsensusService_ChangeConfig_count{${metric_filter}}[$rate_window]))',
            "required": False,
            "categories": ["leader_changes", "replication"],
            "severity": {"warning": {"gt": 0}, "critical": {"gt": 1}},
        },
        "consensus_request_latency_ms": {
            "unit": "ms",
            "query": '(sum by (exported_instance, region) (rate(handler_latency_yb_consensus_ConsensusService_RequestConsensusVotes_sum{${metric_filter}}[$rate_window])) / sum by (exported_instance, region) (rate(handler_latency_yb_consensus_ConsensusService_RequestConsensusVotes_count{${metric_filter}}[$rate_window]))) / 1000',
            "required": False,
            "categories": ["consensus_latency", "replication"],
            "severity": {"warning": {"gt": 250}, "critical": {"gt": 1000}},
        },
        "consensus_change_config_latency_ms": {
            "unit": "ms",
            "query": '(sum by (exported_instance, region) (rate(handler_latency_yb_consensus_ConsensusService_ChangeConfig_sum{${metric_filter}}[$rate_window])) / sum by (exported_instance, region) (rate(handler_latency_yb_consensus_ConsensusService_ChangeConfig_count{${metric_filter}}[$rate_window]))) / 1000',
            "required": False,
            "categories": ["consensus_latency", "replication"],
            "severity": {"warning": {"gt": 250}, "critical": {"gt": 1000}},
        },
        # Master Server metrics.
        "master_avg_latency_ms": {
            "unit": "ms",
            "query": '(sum by (exported_instance, region, service_method) (rate(handler_latency_yb_master_MasterService_sum{${metric_filter}}[$rate_window])) / sum by (exported_instance, region, service_method) (rate(handler_latency_yb_master_MasterService_count{${metric_filter}}[$rate_window]))) / 1000',
            "required": False,
            "categories": ["master_latency", "master_pressure"],
            "severity": {"warning": {"gt": 250}, "critical": {"gt": 1000}},
        },
        "master_get_tablet_locations_rate": {
            "unit": "ops_per_sec",
            "query": 'sum by (exported_instance, region) (rate(handler_latency_yb_master_MasterService_GetTabletLocations_count{${metric_filter}}[$rate_window]))',
            "required": False,
            "categories": ["tablet_location_lookup", "master_pressure"],
            "severity": {"warning": {"gt": 500}, "critical": {"gt": 1000}},
        },
        "master_get_tablet_locations_latency_ms": {
            "unit": "ms",
            "query": '(sum by (exported_instance, region) (rate(handler_latency_yb_master_MasterService_GetTabletLocations_sum{${metric_filter}}[$rate_window])) / sum by (exported_instance, region) (rate(handler_latency_yb_master_MasterService_GetTabletLocations_count{${metric_filter}}[$rate_window]))) / 1000',
            "required": False,
            "categories": ["tablet_location_lookup", "master_latency", "master_pressure"],
            "severity": {"warning": {"gt": 250}, "critical": {"gt": 1000}},
        },
        "master_tsservice_reads_rate": {
            "unit": "ops_per_sec",
            "query": 'sum by (exported_instance, region) (rate(handler_latency_yb_tserver_TabletServerService_Read_count{${metric_filter}, export_type="master_export"}[$rate_window]))',
            "required": False,
            "categories": ["master_tsservice_read", "master_pressure"],
            "severity": {"warning": {"gt": 500}, "critical": {"gt": 1000}},
        },
        "master_tsservice_reads_latency_ms": {
            "unit": "ms",
            "query": '(sum by (exported_instance, region) (rate(handler_latency_yb_tserver_TabletServerService_Read_sum{${metric_filter}, export_type="master_export"}[$rate_window])) / sum by (exported_instance, region) (rate(handler_latency_yb_tserver_TabletServerService_Read_count{${metric_filter}, export_type="master_export"}[$rate_window]))) / 1000',
            "required": False,
            "categories": ["master_tsservice_read", "master_latency", "master_pressure"],
            "severity": {"warning": {"gt": 250}, "critical": {"gt": 1000}},
        },
        "master_tsservice_writes_rate": {
            "unit": "ops_per_sec",
            "query": 'sum by (exported_instance, region) (rate(handler_latency_yb_tserver_TabletServerService_Write_count{${metric_filter}, export_type="master_export"}[$rate_window]))',
            "required": False,
            "categories": ["master_tsservice_write", "master_pressure"],
            "severity": {"warning": {"gt": 100}, "critical": {"gt": 500}},
        },
        "master_tsservice_writes_latency_ms": {
            "unit": "ms",
            "query": '(sum by (exported_instance, region) (rate(handler_latency_yb_tserver_TabletServerService_Write_sum{${metric_filter}, export_type="master_export"}[$rate_window])) / sum by (exported_instance, region) (rate(handler_latency_yb_tserver_TabletServerService_Write_count{${metric_filter}, export_type="master_export"}[$rate_window]))) / 1000',
            "required": False,
            "categories": ["master_tsservice_write", "master_latency", "master_pressure"],
            "severity": {"warning": {"gt": 250}, "critical": {"gt": 1000}},
        },
        "master_update_consensus_rate": {
            "unit": "ops_per_sec",
            "query": 'sum by (exported_instance, region) (rate(handler_latency_yb_consensus_ConsensusService_UpdateConsensus_count{${metric_filter}, export_type="master_export"}[$rate_window]))',
            "required": False,
            "categories": ["master_consensus", "replication"],
            "severity": {"warning": {"gt": 500}, "critical": {"gt": 1000}},
        },
        "master_update_consensus_latency_ms": {
            "unit": "ms",
            "query": '(sum by (exported_instance, region) (rate(handler_latency_yb_consensus_ConsensusService_UpdateConsensus_sum{${metric_filter}, export_type="master_export"}[$rate_window])) / sum by (exported_instance, region) (rate(handler_latency_yb_consensus_ConsensusService_UpdateConsensus_count{${metric_filter}, export_type="master_export"}[$rate_window]))) / 1000',
            "required": False,
            "categories": ["master_consensus", "consensus_latency", "replication"],
            "severity": {"warning": {"gt": 250}, "critical": {"gt": 1000}},
        },
        "master_multiraft_update_consensus_rate": {
            "unit": "ops_per_sec",
            "query": 'sum by (exported_instance, region) (rate(handler_latency_yb_consensus_ConsensusService_MultiRaftUpdateConsensus_count{${metric_filter}, export_type="master_export"}[$rate_window]))',
            "required": False,
            "categories": ["master_consensus", "replication"],
            "severity": {"warning": {"gt": 500}, "critical": {"gt": 1000}},
        },
        "master_multiraft_update_consensus_latency_ms": {
            "unit": "ms",
            "query": '(sum by (exported_instance, region) (rate(handler_latency_yb_consensus_ConsensusService_MultiRaftUpdateConsensus_sum{${metric_filter}, export_type="master_export"}[$rate_window])) / sum by (exported_instance, region) (rate(handler_latency_yb_consensus_ConsensusService_MultiRaftUpdateConsensus_count{${metric_filter}, export_type="master_export"}[$rate_window]))) / 1000',
            "required": False,
            "categories": ["master_consensus", "consensus_latency", "replication"],
            "severity": {"warning": {"gt": 250}, "critical": {"gt": 1000}},
        },
        "master_create_delete_table_rpcs": {
            "unit": "ops_per_sec",
            "query": 'sum by (exported_instance, region) (rate(handler_latency_yb_master_MasterService_CreateTable_count{${metric_filter}}[$rate_window]) + rate(handler_latency_yb_master_MasterService_DeleteTable_count{${metric_filter}}[$rate_window]))',
            "required": False,
            "categories": ["ddl_activity", "master_pressure"],
            "severity": {"warning": {"gt": 0}, "critical": {"gt": 1}},
        },
        "master_threads_running": {
            "unit": "threads",
            "query": 'sum by (exported_instance, region) (server_threads_running{${metric_filter}, export_type="master_export"})',
            "required": False,
            "categories": ["thread_pressure", "master_pressure"],
            "severity": {"warning": {"gt": 200}, "critical": {"gt": 500}},
        },
        "master_wal_latency_ms": {
            "unit": "ms",
            "query": '(sum by (exported_instance, region) (rate(log_append_latency_sum{${metric_filter}, export_type="master_export"}[$rate_window]) + rate(log_sync_latency_sum{${metric_filter}, export_type="master_export"}[$rate_window])) / sum by (exported_instance, region) (rate(log_append_latency_count{${metric_filter}, export_type="master_export"}[$rate_window]) + rate(log_sync_latency_count{${metric_filter}, export_type="master_export"}[$rate_window]))) / 1000',
            "required": False,
            "categories": ["master_wal_latency", "master_pressure", "storage_pressure"],
            "severity": {"warning": {"gt": 50}, "critical": {"gt": 250}},
        },
        "master_wal_bytes_written": {
            "unit": "bytes_per_sec",
            "query": 'sum by (exported_instance, region) (rate(log_bytes_logged{${metric_filter}, export_type="master_export"}[$rate_window]))',
            "required": False,
            "categories": ["master_wal_pressure", "master_pressure"],
            "severity": {"warning": {"gt": 50000000}, "critical": {"gt": 200000000}},
        },
        "master_wal_bytes_read": {
            "unit": "bytes_per_sec",
            "query": 'sum by (exported_instance, region) (rate(log_bytes_read{${metric_filter}, export_type="master_export"}[$rate_window]))',
            "required": False,
            "categories": ["master_wal_pressure", "master_pressure"],
            "severity": {"warning": {"gt": 50000000}, "critical": {"gt": 200000000}},
        },
        # Advanced memory/logging/DocDB metrics used by both master and tserver views.
        "tcmalloc_in_use_bytes": {
            "unit": "bytes",
            "query": 'sum by (exported_instance, region, export_type) (generic_heap_size{${metric_filter}})',
            "required": False,
            "categories": ["tcmalloc_pressure", "memory_pressure"],
            "severity": {},
        },
        "tcmalloc_reserved_bytes": {
            "unit": "bytes",
            "query": 'sum by (exported_instance, region, export_type) (generic_current_allocated_bytes{${metric_filter}})',
            "required": False,
            "categories": ["tcmalloc_pressure", "memory_pressure"],
            "severity": {},
        },
        "glog_messages_rate": {
            "unit": "messages_per_sec",
            "query": 'sum by (exported_instance, region, level, export_type) (rate(glog_info_messages{${metric_filter}}[$rate_window]) + rate(glog_warning_messages{${metric_filter}}[$rate_window]) + rate(glog_error_messages{${metric_filter}}[$rate_window]))',
            "required": False,
            "categories": ["glog_messages", "observability"],
            "severity": {"warning": {"gt": 1}, "critical": {"gt": 10}},
        },
        "lsm_seek_next_ops": {
            "unit": "ops_per_sec",
            "query": 'sum by (exported_instance, region, table_name) (rate(rocksdb_number_db_seek{${metric_filter}}[$rate_window]) + rate(rocksdb_number_db_next{${metric_filter}}[$rate_window]))',
            "required": False,
            "categories": ["lsm_seek_pressure", "storage_pressure"],
            "severity": {"warning": {"gt": 10000}, "critical": {"gt": 100000}},
        },
        "lsm_seeks_rate": {
            "unit": "ops_per_sec",
            "query": 'sum by (exported_instance, region, table_name) (rate(rocksdb_number_db_seek{${metric_filter}}[$rate_window]))',
            "required": False,
            "categories": ["lsm_seek_pressure", "storage_pressure"],
            "severity": {"warning": {"gt": 10000}, "critical": {"gt": 100000}},
        },
        "sstable_size_bytes": {
            "unit": "bytes",
            "query": 'sum by (exported_instance, region, table_name) (rocksdb_current_version_sst_files_size{${metric_filter}})',
            "required": False,
            "categories": ["sstable_pressure", "storage_pressure"],
            "severity": {"warning": {"gt": 100000000000}, "critical": {"gt": 500000000000}},
        },
        "average_sstables_per_node": {
            "unit": "count",
            "query": 'avg by (exported_instance, region, table_name) (rocksdb_num_sst_files{${metric_filter}})',
            "required": False,
            "categories": ["sstable_pressure", "storage_pressure"],
            "severity": {"warning": {"gt": 24}, "critical": {"gt": 48}},
        },
        "docdb_get_latency_ms": {
            "unit": "ms",
            "query": '(sum by (exported_instance, region, table_name) (rate(rocksdb_get_micros_sum{${metric_filter}}[$rate_window])) / sum by (exported_instance, region, table_name) (rate(rocksdb_get_micros_count{${metric_filter}}[$rate_window]))) / 1000',
            "required": False,
            "categories": ["docdb_get_latency", "docdb_read_latency", "storage_pressure"],
            "severity": {"warning": {"gt": 50}, "critical": {"gt": 250}},
        },
        "docdb_write_latency_ms": {
            "unit": "ms",
            "query": '(sum by (exported_instance, region, table_name) (rate(rocksdb_write_micros_sum{${metric_filter}}[$rate_window])) / sum by (exported_instance, region, table_name) (rate(rocksdb_write_micros_count{${metric_filter}}[$rate_window]))) / 1000',
            "required": False,
            "categories": ["docdb_write_latency", "storage_pressure"],
            "severity": {"warning": {"gt": 50}, "critical": {"gt": 250}},
        },
        "docdb_seek_latency_ms": {
            "unit": "ms",
            "query": '(sum by (exported_instance, region, table_name) (rate(rocksdb_seek_micros_sum{${metric_filter}}[$rate_window])) / sum by (exported_instance, region, table_name) (rate(rocksdb_seek_micros_count{${metric_filter}}[$rate_window]))) / 1000',
            "required": False,
            "categories": ["docdb_seek_latency", "docdb_read_latency", "storage_pressure"],
            "severity": {"warning": {"gt": 50}, "critical": {"gt": 250}},
        },
        "docdb_mutex_wait_latency_ms": {
            "unit": "ms",
            "query": '(sum by (exported_instance, region, table_name) (rate(rocksdb_db_mutex_wait_micros_sum{${metric_filter}}[$rate_window])) / sum by (exported_instance, region, table_name) (rate(rocksdb_db_mutex_wait_micros_count{${metric_filter}}[$rate_window]))) / 1000',
            "required": False,
            "categories": ["docdb_mutex_wait", "storage_pressure"],
            "severity": {"warning": {"gt": 50}, "critical": {"gt": 250}},
        },
        "block_cache_hit_rate": {
            "unit": "events_per_sec",
            "query": 'sum by (exported_instance, region, table_name) (rate(rocksdb_block_cache_hit{${metric_filter}}[$rate_window]))',
            "required": False,
            "categories": ["cache_pressure", "storage_pressure"],
            "severity": {},
        },
        "block_cache_usage_bytes": {
            "unit": "bytes",
            "query": 'sum by (exported_instance, region, table_name) (rocksdb_block_cache_usage{${metric_filter}})',
            "required": False,
            "categories": ["cache_pressure", "memory_pressure", "storage_pressure"],
            "severity": {},
        },
        "bloom_checked_rate": {
            "unit": "events_per_sec",
            "query": 'sum by (exported_instance, region, table_name) (rate(rocksdb_bloom_filter_checked{${metric_filter}}[$rate_window]))',
            "required": False,
            "categories": ["bloom_filter", "storage_pressure"],
            "severity": {},
        },
        "bloom_useful_rate": {
            "unit": "events_per_sec",
            "query": 'sum by (exported_instance, region, table_name) (rate(rocksdb_bloom_filter_useful{${metric_filter}}[$rate_window]))',
            "required": False,
            "categories": ["bloom_filter", "storage_pressure"],
            "severity": {},
        },
        "compaction_bytes": {
            "unit": "bytes_per_sec",
            "query": 'sum by (exported_instance, region, table_name) (rate(rocksdb_compact_read_bytes{${metric_filter}}[$rate_window]) + rate(rocksdb_compact_write_bytes{${metric_filter}}[$rate_window]))',
            "required": False,
            "categories": ["compaction_pressure", "storage_pressure"],
            "severity": {"warning": {"gt": 50000000}, "critical": {"gt": 200000000}},
        },
        "compaction_num_files": {
            "unit": "count",
            "query": 'avg by (exported_instance, region, table_name) (rocksdb_num_files_in_single_compaction{${metric_filter}})',
            "required": False,
            "categories": ["compaction_pressure", "storage_pressure"],
            "severity": {"warning": {"gt": 8}, "critical": {"gt": 16}},
        },
        "docdb_rejections": {
            "unit": "events_per_sec",
            "query": 'sum by (exported_instance, region, table_name) (rate(rocksdb_rejections{${metric_filter}}[$rate_window]))',
            "required": False,
            "categories": ["docdb_rejections", "storage_pressure"],
            "severity": {"warning": {"gt": 0}, "critical": {"gt": 1}},
        },
        "transaction_expired": {
            "unit": "events_per_sec",
            "query": 'sum by (exported_instance, region) (rate(transaction_expired{${metric_filter}}[$rate_window]))',
            "required": False,
            "categories": ["transaction_contention", "txn_expired"],
            "severity": {"warning": {"gt": 1}, "critical": {"gt": 10}},
        },
        "transaction_pool_cache_hits": {
            "unit": "ratio",
            "query": 'avg by (exported_instance, region) (transaction_pool_cache_hits{${metric_filter}})',
            "required": False,
            "categories": ["transaction_contention"],
            "severity": {},
        },
    }
)


def is_ycql_metric(metric_name: str) -> bool:
    return bool(YCQL_EXCLUDE_RE.search(metric_name))


def should_discover_metric(metric_name: str, include_re: re.Pattern[str] | None = None) -> bool:
    if is_ycql_metric(metric_name) or HISTOGRAM_BUCKET_RE.search(metric_name):
        return False
    if include_re and not include_re.search(metric_name):
        return False
    return True


def discovered_metric_definition(metric_name: str, metric_filter: str) -> dict[str, Any]:
    categories = infer_categories(metric_name)
    query = discovered_query(metric_name, metric_filter)
    unit = infer_unit(metric_name)
    return {
        "unit": unit,
        "query": query,
        "required": False,
        "discovered": True,
        "categories": categories,
        "severity": inferred_severity(categories, unit),
    }


def discovered_query(metric_name: str, metric_filter: str) -> str:
    selector = f'{metric_name}{{{metric_filter}}}'
    if COUNTER_RE.search(metric_name):
        return f"sum by (exported_instance, region) (rate({selector}[$rate_window]))"
    return f"max by (exported_instance, region) ({selector})"


def infer_categories(metric_name: str) -> list[str]:
    name = metric_name.lower()
    categories: list[str] = []
    if "ysql" in name or "sql" in name:
        categories.extend(["ysql_read_latency" if "latency" in name else "ysql_ops", "latency" if "latency" in name else "workload"])
    if "catalog" in name:
        categories.extend(["catalog_cache_miss", "master_pressure"])
    if "rpc" in name or "rpcs" in name:
        categories.extend(["rpc_queue_size" if "queue" in name else "rpc", "rpc_timeout_rate" if "timeout" in name else "rpc"])
    if "consensus" in name or "raft" in name or "leader" in name or "bootstrap" in name:
        categories.extend(["consensus_latency" if "latency" in name else "replication", "replication"])
    if "follower" in name or "lag" in name:
        categories.extend(["follower_lag_spike", "replication"])
    if "wal" in name or name.startswith("log_"):
        categories.extend(["wal_latency" if "latency" in name else "wal_pressure", "storage_pressure"])
    if any(token in name for token in ("rocksdb", "lsm", "sst", "compaction", "flush", "stall")):
        categories.extend(["rocksdb_stalls" if "stall" in name else "storage_pressure", "storage_pressure"])
    if "cache" in name or "bloom" in name:
        categories.extend(["cache_miss" if "miss" in name else "cache_pressure", "storage_pressure"])
    if "transaction" in name or "conflict" in name or "lock" in name:
        categories.extend(["txn_conflicts" if "conflict" in name else "transaction_contention", "transaction_contention"])
    if "cpu" in name or "load" in name or "context_switch" in name:
        categories.extend(["cpu_pressure", "resource_pressure"])
    if "mem" in name or "tcmalloc" in name:
        categories.append("memory_pressure")
    if "disk" in name or "iowait" in name:
        categories.extend(["iowait" if "iowait" in name else "disk_iops", "storage_pressure"])
    if "network" in name or "tcp" in name or "retrans" in name or "packet" in name:
        categories.extend(["tcp_retransmits" if "retrans" in name else "network_errors", "network"])
    if "clock" in name:
        categories.extend(["clock_skew", "clock"])
    if "master" in name:
        categories.append("master_pressure")
    if not categories:
        categories.append("observability")
    return list(dict.fromkeys(categories))


def infer_unit(metric_name: str) -> str:
    name = metric_name.lower()
    if "latency" in name or "micros" in name:
        return "microseconds"
    if "bytes" in name:
        return "bytes"
    if "seconds" in name:
        return "seconds"
    if COUNTER_RE.search(metric_name):
        return "per_sec"
    return "value"


def inferred_severity(categories: list[str], unit: str) -> dict[str, dict[str, float]]:
    category_set = set(categories)
    if "clock_skew" in category_set:
        return {"warning": {"gt": 250000}, "critical": {"gt": 500000}}
    if category_set & {"rpc_timeout_rate", "rpc_overflow_rate", "network_errors", "tcp_retransmits"}:
        return {"warning": {"gt": 0}, "critical": {"gt": 1}}
    if category_set & {"rocksdb_stalls", "txn_conflicts", "leader_changes", "remote_bootstrap"}:
        return {"warning": {"gt": 0}, "critical": {"gt": 10}}
    if "iowait" in category_set:
        return {"warning": {"gt": 0.15}, "critical": {"gt": 0.25}}
    if unit in {"microseconds", "ms"} or "latency" in category_set:
        return {"warning": {"gt": 500000}, "critical": {"gt": 5000000}}
    return {}
