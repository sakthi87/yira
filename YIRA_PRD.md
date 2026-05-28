# PRD: YugabyteDB YSQL Incident Root Cause Analyzer (YIRA)

## 1. Executive Summary

YIRA is a YBA-aware incident analysis system for YugabyteDB YSQL universes. It collects metrics, logs, and optional SQL snapshots around a latency incident window, detects subsystem anomalies, correlates signals across YSQL, DocDB, Raft, storage, network, node, and workload layers, and produces a ranked root cause analysis with evidence, confidence, suspected nodes, suspected regions, and next diagnostic actions.

The first target environment is a 10-node, 3-region YugabyteDB universe with a `4 + 4 + 2` placement pattern, Spark write workload, API read workload, and intermittent read latency spikes such as `50ms -> 10s`. The product must not be hard-coded to this topology. Topology, region weights, thresholds, metric names, correlation windows, query templates, log rules, workload rules, and scoring weights must be configuration driven.

Primary design principle:

> In a distributed SQL system, user-visible read latency is often cluster health latency, not only SQL execution latency.

## 2. Problem Statement

Intermittent YSQL latency spikes are difficult to diagnose because the symptom often appears in one layer while the cause originates in another:

- API reads may wait on safe time, transaction status, remote tablet access, RPC queues, or overloaded Raft followers.
- Spark writes may increase Raft replication pressure, WAL pressure, compaction work, or RPC contention.
- A single hot tablet or slow node can affect a fraction of reads and look random from the application.
- Three-region placement increases sensitivity to leader placement, cross-region RPC latency, clock skew, and regional quorum behavior.
- Incidents disappear before engineers can manually inspect `pg_stat_activity`, YBA dashboards, logs, and tablet status.

YIRA must provide a repeatable evidence-driven workflow that answers:

- What happened?
- When did it start and stop?
- Which nodes, regions, services, tables, tablets, or query classes were involved?
- Which subsystem most likely caused the latency?
- What supporting evidence exists?
- What evidence is missing?
- What should be checked next?

## 3. Goals

- Analyze a specific incident window using YBA Prometheus as the default metric backend.
- Support YSQL read latency incidents, replication delay, follower lag, safe-time waits, RPC saturation, network instability, storage stalls, hot tablets, leader skew, transaction contention, and workload-induced pressure.
- Support 3-region universes, including asymmetric placements such as `4 + 4 + 2`.
- Support parameterized metric names and PromQL templates because metric availability and labels can differ by YugabyteDB/YBA version and deployment style.
- Correlate time-series anomalies with logs and optional SQL snapshots.
- Produce both human-readable and machine-readable output.
- Run as a CLI first, with a service/dashboard mode as a later milestone.
- Complete a typical 30 to 60 minute incident analysis in under 2 minutes for a 10-node universe.

## 4. Non-Goals

- YIRA is not a query optimizer.
- YIRA does not replace Grafana, Prometheus, YBA dashboards, or application tracing.
- YIRA does not mutate the universe or perform automatic remediation in the initial release.
- YIRA does not require external Prometheus, although it may support one as an alternate backend.
- YIRA does not guarantee a single root cause when evidence supports multiple interacting causes.

## 5. Personas

- Database SRE: needs fast incident triage and node/region evidence.
- Application engineer: needs to know whether API latency came from SQL/query shape, cluster health, workload pressure, or contention.
- Data platform engineer: needs to determine whether Spark write jobs are correlated with read latency.
- DBA/platform owner: needs repeatable RCA reports for postmortems and capacity planning.

## 6. Data Sources

### 6.1 Required Sources

- YBA Prometheus compatible API:
  - `/api/v1/query_range`
  - `/api/v1/query`
- YugabyteDB service metrics exposed through YBA:
  - YB-Master metrics from `:7000/prometheus-metrics`
  - YB-TServer metrics from `:9000/prometheus-metrics`
  - YSQL metrics from `:13000/prometheus-metrics`

### 6.2 Optional Sources

- YBA universe metadata API for node, region, AZ, process, and placement mapping.
- Node exporter or YBA-provided node metrics for CPU, iowait, disk, memory, network, and TCP retransmits.
- TServer and Master logs.
- YSQL snapshots:
  - `pg_stat_activity`
  - `pg_stat_statements`
  - `pg_locks`
  - `yb_terminated_queries`
  - `pg_stat_progress_copy`
- Application workload metrics:
  - Spark job metrics
  - API service latency
  - request rate
  - error rate
  - read/write mix
- Cloud metrics:
  - EBS / disk queue
  - ENA / NIC drops
  - VM steal time
  - load balancer metrics

## 7. Functional Requirements

### 7.1 Incident Window Analysis

The user provides either:

- explicit start and end timestamps, or
- an approximate incident timestamp plus lookback/lookahead buffers.

YIRA must expand the analysis window into:

- baseline window before incident,
- incident window,
- recovery window after incident.

Example:

```yaml
window:
  incident_start: "2026-05-26T10:00:00Z"
  incident_end: "2026-05-26T10:30:00Z"
  baseline:
    before: "30m"
  recovery:
    after: "15m"
  step: "30s"
```

### 7.2 Universe Topology Awareness

YIRA must understand node identity, placement, and role:

```yaml
topology:
  expected_node_count: 10
  regions:
    - name: us-west-2
      expected_nodes: 4
      preferred: true
    - name: us-east-1
      expected_nodes: 4
    - name: us-central-1
      expected_nodes: 2
  replication_factor: 3
  placement_pattern: "4+4+2"
  leader_preference:
    enabled: true
    preferred_regions: ["us-west-2"]
```

The analyzer must aggregate signals at these levels:

- cluster
- region
- AZ
- node
- process/service
- table
- tablet, if available
- workload

### 7.3 Metric Discovery

YIRA must support both static and dynamic metric discovery:

- Static registry of known YugabyteDB metric families.
- Runtime discovery through Prometheus label and metric-name queries.
- Alias mapping for renamed metrics or relabeled metrics.
- Version-specific metric packs.
- Validation report for missing metrics.

Metric availability must not break the analyzer. Missing evidence should reduce confidence and appear in the report.

### 7.4 Metric Collection

YIRA must collect metrics in categories:

- YSQL query latency and throughput
- YSQL connections and backend state
- RPC queue depth, timeout, overflow, and handler latency
- Raft consensus latency, elections, leader changes, and remote bootstrap
- follower lag and replication delay
- safe-time lag and read wait indicators
- transaction conflicts, restarts, lock waits, and deadlocks
- DocDB / RocksDB storage pressure
- WAL, flush, compaction, block cache, bloom filter, memtable pressure
- node CPU, iowait, memory, disk queue, disk latency, disk throughput
- network retransmits, drops, bandwidth, cross-region latency proxies
- clock skew
- load skew and hot tablet indicators
- master/tablet management events
- Spark/API workload metrics, if supplied

### 7.5 Log Collection

YIRA must support log ingestion from:

- local files,
- SSH/SFTP pull,
- object storage,
- YBA support bundles,
- user-provided directories.

Logs must be parsed using configurable patterns:

```yaml
logs:
  enabled: true
  sources:
    - type: local
      path: "./logs"
  services: ["tserver", "master", "ysql"]
  time_tolerance: "2m"
  rulesets:
    - yugabyte_default
    - custom_org_rules
  patterns:
    rpc_timeout:
      severity: critical
      regex: "(?i)(timed out|deadline expired|service unavailable)"
      categories: ["rpc", "latency"]
    raft_election:
      severity: warning
      regex: "(?i)(election|leader changed|RequestConsensusVotes)"
      categories: ["raft"]
    remote_bootstrap:
      severity: warning
      regex: "(?i)(remote bootstrap|StartRemoteBootstrap)"
      categories: ["raft", "tablet"]
    disk_stall:
      severity: critical
      regex: "(?i)(stall|slow.*write|fsync.*slow|rocksdb)"
      categories: ["storage"]
```

### 7.6 Optional SQL Snapshot Collection

When YSQL connectivity is configured, YIRA should collect bounded snapshots:

```yaml
ysql_snapshots:
  enabled: true
  connection:
    host: "yb-ysql-endpoint"
    port: 5433
    database: "yugabyte"
    user_env: "YIRA_YSQL_USER"
    password_env: "YIRA_YSQL_PASSWORD"
    connect_timeout: "5s"
    statement_timeout: "10s"
  collect:
    pg_stat_activity: true
    pg_stat_statements: true
    pg_locks: true
    yb_terminated_queries: true
  query_text_policy:
    capture: false
    normalize: true
    redact_literals: true
```

YIRA must treat SQL text as sensitive. Default output should redact query text and show query fingerprints or hashes unless explicitly enabled.

## 8. Metric Registry

Metric definitions must live in configuration, not code. Each metric definition includes:

- logical name
- source
- PromQL template
- unit
- directionality
- severity thresholds
- baseline anomaly settings
- labels to preserve
- aggregation strategy
- root-cause categories affected

Example:

```yaml
metrics:
  ysql_select_latency_p99:
    source: prometheus
    unit: ms
    query: |
      histogram_quantile(
        0.99,
        sum by (le, exported_instance, region) (
          rate(handler_latency_yb_ysqlserver_SQLProcessor_SelectStmt_bucket{universe="$universe"}[$rate_window])
        )
      ) / 1000
    required: false
    labels: ["exported_instance", "region"]
    aggregate: ["max", "p95", "avg"]
    severity:
      warning: { gt: 500 }
      critical: { gt: 5000 }

  consensus_update_latency_p99:
    source: prometheus
    unit: ms
    query: |
      histogram_quantile(
        0.99,
        sum by (le, exported_instance, region) (
          rate(handler_latency_yb_consensus_ConsensusService_UpdateConsensus_bucket{universe="$universe"}[$rate_window])
        )
      ) / 1000
    required: true
    labels: ["exported_instance", "region"]
    categories: ["raft", "replication"]

  rpc_queue_size:
    source: prometheus
    unit: count
    query: |
      sum by (exported_instance, service_type, service_method) (
        rpcs_in_queue{universe="$universe"}
      )
    required: true
    categories: ["rpc"]

  rpc_queue_overflow_rate:
    source: prometheus
    unit: events_per_sec
    query: |
      sum by (exported_instance, service_type, service_method) (
        rate(rpcs_queue_overflow{universe="$universe"}[$rate_window])
      )
    required: false
    categories: ["rpc", "overload"]

  clock_skew_ms:
    source: prometheus
    unit: ms
    query: |
      max by (exported_instance, region) (
        hybrid_clock_skew{universe="$universe"} / 1000
      )
    required: false
    categories: ["clock", "consistency", "latency"]
```

Important note: YugabyteDB service endpoints expose database/service metrics. System-level CPU, iowait, disk, and network metrics require YBA-provided node metrics, node exporter, cloud metrics, or another configured source.

## 9. Normalization

YIRA must normalize all collected data into a common event model:

```json
{
  "timestamp": "2026-05-26T10:05:30Z",
  "source": "prometheus",
  "metric": "rpc_queue_size",
  "value": 42,
  "unit": "count",
  "severity": "critical",
  "node": "node-7",
  "region": "us-east-1",
  "service": "tserver",
  "labels": {
    "service_type": "TabletServerService",
    "service_method": "Read"
  }
}
```

All timestamps must be bucketed to the configured step, commonly `30s` or `60s`.

## 10. Signal Detection

Each signal receives:

- severity: `normal`, `info`, `warning`, `critical`
- score: `0.0 - 1.0`
- affected entities
- supporting samples
- baseline deviation
- duration
- first seen / last seen

Supported detection modes:

```yaml
detection:
  default_bucket: "30s"
  min_duration_buckets: 2
  methods:
    static_threshold: true
    baseline_zscore: true
    mad: true
    rate_of_change: true
    node_skew: true
    region_skew: true
    seasonality: false
  baseline:
    lookback: "30m"
    min_points: 20
  zscore:
    warning: 2.5
    critical: 4.0
  mad:
    warning: 3.5
    critical: 6.0
```

### 10.1 Example Signal Rules

```yaml
signal_rules:
  follower_lag_spike:
    metric: follower_lag_ms
    warning:
      any:
        - gt: 1000
        - baseline_multiplier_gt: 3
    critical:
      any:
        - gt: 5000
        - baseline_multiplier_gt: 10
    min_duration: "60s"

  rpc_saturation:
    metrics: ["rpc_queue_size", "rpc_queue_overflow_rate", "rpc_timeout_rate"]
    critical:
      all:
        - rpc_queue_size.p95_gt: 10
        - any:
            - rpc_queue_overflow_rate.gt: 0
            - rpc_timeout_rate.gt: 0

  node_storage_pressure:
    metrics: ["node_iowait_ratio", "disk_await_ms", "rocksdb_stall_rate", "flush_latency_ms"]
    warning:
      any:
        - node_iowait_ratio.gt: 0.15
        - disk_await_ms.gt: 20
    critical:
      any:
        - node_iowait_ratio.gt: 0.25
        - rocksdb_stall_rate.gt: 0
```

## 11. Correlation Engine

The correlation engine must evaluate whether signals overlap in time, entity, and causal direction.

### 11.1 Correlation Dimensions

- Time overlap: same bucket or within configured lag.
- Entity overlap: same node, region, service, table, tablet.
- Causal order: suspected cause appears before or at same time as symptom.
- Blast radius: one node, one region, all regions, specific table, specific tablet.
- Workload phase: Spark batch start/end, API traffic surge, maintenance event.

### 11.2 Correlation Configuration

```yaml
correlation:
  bucket: "30s"
  max_lag:
    storage_to_replication: "3m"
    network_to_raft: "2m"
    workload_to_rpc: "5m"
    raft_to_read_latency: "2m"
    clock_to_read_latency: "1m"
  entity_match_weights:
    same_node: 1.0
    same_region: 0.7
    cluster_wide: 0.5
    no_match: 0.1
  minimum_correlation_score: 0.35
```

### 11.3 Core Correlation Rules

#### Replication Delay -> Read Latency

```text
IF follower lag or consensus update latency rises
AND safe-time/read latency rises within max_lag
AND affected nodes/regions overlap
THEN replication delay is a candidate root cause
```

#### Storage Pressure -> Replication Delay

```text
IF disk latency/iowait/rocksdb stall/flush/compaction pressure rises
AND Raft UpdateConsensus latency or follower lag rises afterward
THEN storage pressure is a candidate upstream cause
```

#### RPC Saturation -> Read Latency

```text
IF rpcs_in_queue rises
AND queue timeout or overflow appears
AND handler latency or YSQL latency rises
THEN RPC saturation/thread starvation is a candidate root cause
```

#### Spark Write Pressure -> Read Impact

```text
IF Spark write throughput/batch concurrency rises
AND write path latency/Raft replication/WAL/compaction/RPC queue rises
AND API read latency rises afterward
THEN workload-induced write pressure is a candidate contributing cause
```

#### Network Instability -> Raft Delay

```text
IF retransmits/drops/cross-region latency proxies rise
AND consensus latency/elections/follower lag rise
THEN network instability is a candidate root cause
```

#### Clock Skew -> Read Waits

```text
IF hybrid_clock_skew rises
AND read latency/safe-time wait indicators rise
THEN clock instability is a candidate root cause
```

#### Hot Tablet / Leader Skew

```text
IF latency or queue pressure is concentrated on a small node/tablet set
AND cluster-level CPU/storage is otherwise normal
AND tablet peer or leader distribution is skewed
THEN hot tablet or leader skew is a candidate root cause
```

#### Transaction Contention

```text
IF transaction conflicts/restarts/lock waits rise
AND YSQL read or write latency rises
AND storage/RPC/network evidence is weak
THEN transaction contention is a candidate root cause
```

## 12. Root Cause Inference

Root causes are scored using weighted evidence. Scores must be configurable.

```yaml
root_causes:
  replication_delay:
    enabled: true
    threshold: 0.70
    weights:
      follower_lag_spike: 0.30
      consensus_update_latency: 0.25
      safe_time_lag: 0.25
      ysql_read_latency: 0.10
      log_raft_warnings: 0.10

  storage_bottleneck:
    enabled: true
    threshold: 0.70
    weights:
      node_iowait: 0.20
      disk_await: 0.20
      rocksdb_stalls: 0.20
      flush_or_compaction_latency: 0.20
      wal_latency: 0.10
      downstream_replication_delay: 0.10

  rpc_saturation:
    enabled: true
    threshold: 0.70
    weights:
      rpc_queue_size: 0.25
      rpc_timeout_rate: 0.20
      rpc_overflow_rate: 0.20
      handler_latency: 0.20
      log_deadline_expired: 0.15

  network_instability:
    enabled: true
    threshold: 0.70
    weights:
      tcp_retransmits: 0.25
      packet_drops: 0.20
      consensus_latency: 0.25
      elections_or_vote_requests: 0.15
      region_specific_impact: 0.15

  workload_pressure:
    enabled: true
    threshold: 0.65
    weights:
      spark_write_throughput: 0.20
      ysql_write_latency: 0.15
      wal_or_flush_pressure: 0.15
      consensus_latency: 0.20
      rpc_queue_size: 0.15
      read_latency_after_write_surge: 0.15

  hot_tablet_or_leader_skew:
    enabled: true
    threshold: 0.65
    weights:
      node_skew: 0.25
      tablet_peer_skew: 0.20
      leader_skew: 0.20
      localized_rpc_or_latency: 0.20
      table_specific_evidence: 0.15

  transaction_contention:
    enabled: true
    threshold: 0.65
    weights:
      txn_conflicts: 0.25
      read_restarts: 0.20
      lock_waits: 0.20
      pg_locks_evidence: 0.20
      weak_infra_evidence: 0.15
```

### 12.1 Confidence Bands

```yaml
confidence:
  high: 0.80
  medium: 0.60
  low: 0.40
  insufficient_evidence_below: 0.40
```

### 12.2 Tie Handling

If multiple root causes exceed threshold:

- identify primary cause by highest causal precedence,
- list contributing causes,
- show competing hypotheses,
- explain missing data that would break the tie.

Example:

```text
Primary: storage bottleneck on node-7
Contributing: replication delay, RPC queue buildup
Why: disk latency rose 90s before follower lag and RPC queue buildup on the same node.
```

## 13. 4+4+2 Three-Region Considerations

The analyzer must include topology-specific checks:

- Does the 2-node region show disproportionate follower lag or read latency?
- Are tablet leaders concentrated in one of the 4-node regions?
- Are API reads routed to a non-preferred or remote region?
- Did the incident align with cross-region replication latency?
- Did a node in the 2-node region become a bottleneck because fewer peers share regional load?
- Is quorum behavior sensitive to a region-level impairment?
- Are read replicas, leader preferences, tablespaces, or placement policies involved?

Example topology rule:

```yaml
topology_rules:
  asymmetric_region_pressure:
    enabled: true
    description: "Detect whether the 2-node region is overloaded relative to 4-node regions."
    metric_groups: ["ysql_latency", "rpc_queue", "consensus_latency", "follower_lag"]
    compare:
      method: "per_node_region_normalized"
      warning_ratio: 1.5
      critical_ratio: 2.5
```

## 14. Output Requirements

### 14.1 Human Report

The report must include:

- incident summary,
- timeline,
- root cause ranking,
- evidence table,
- affected nodes/regions/services,
- correlated workload events,
- log highlights,
- missing evidence,
- recommended next diagnostics,
- machine-readable output path.

Example:

```text
Incident Summary

Window:
2026-05-26 10:00:00Z to 10:30:00Z

Symptom:
YSQL SELECT p99 latency increased from 55ms baseline to 10.2s peak.

Primary Root Cause:
Replication delay driven by RPC saturation during Spark write pressure.

Confidence:
High (0.84)

Key Evidence:
- Consensus UpdateConsensus p99 increased from 80ms to 3.8s.
- rpcs_in_queue on node-7 and node-8 increased 5.4x.
- follower_lag_ms peaked at 5816ms in us-east-1.
- API read p99 rose 60s after Spark write throughput increased.
- TServer logs showed deadline exceeded messages during the same buckets.

Contributing Factors:
- Region-normalized pressure was highest in the 2-node region.
- No strong storage stall evidence was observed.

Recommended Next Actions:
- Check leader distribution and hot tablets for affected tables.
- Validate Spark batch concurrency and write batch size during incident.
- Inspect TServer thread pool sizing and RPC timeout/overflow counters.
```

### 14.2 JSON Report

```json
{
  "incident_id": "2026-05-26T10-00Z-prod-yugabyte",
  "window": {
    "start": "2026-05-26T10:00:00Z",
    "end": "2026-05-26T10:30:00Z",
    "step": "30s"
  },
  "symptom": {
    "name": "ysql_select_latency_spike",
    "baseline_p99_ms": 55,
    "peak_p99_ms": 10200
  },
  "primary_root_cause": {
    "category": "replication_delay",
    "confidence": 0.84,
    "confidence_band": "high"
  },
  "contributing_causes": [
    {
      "category": "rpc_saturation",
      "confidence": 0.78
    },
    {
      "category": "workload_pressure",
      "confidence": 0.71
    }
  ],
  "affected_entities": {
    "regions": ["us-east-1"],
    "nodes": ["node-7", "node-8"],
    "services": ["tserver", "ysql"]
  },
  "signals": [
    {
      "name": "consensus_update_latency",
      "severity": "critical",
      "peak": 3800,
      "unit": "ms"
    },
    {
      "name": "rpc_queue_size",
      "severity": "critical",
      "peak": 42,
      "unit": "count"
    }
  ],
  "missing_evidence": [
    "node_exporter tcp retransmit metrics unavailable",
    "safe-time metric alias not configured"
  ],
  "recommendations": [
    "Inspect leader distribution for affected tables",
    "Check Spark write concurrency during incident",
    "Review TServer RPC queue timeout and overflow metrics"
  ]
}
```

## 15. CLI Requirements

### 15.1 Commands

```bash
yira analyze --config yira.yaml
yira discover --config yira.yaml
yira validate-config --config yira.yaml
yira list-metrics --prometheus-url http://yba-host:9090
yira explain --report reports/incident.json
yira compare --baseline baseline.json --incident incident.json
```

### 15.2 Exit Codes

- `0`: completed successfully
- `1`: analysis completed with low confidence
- `2`: config invalid
- `3`: data source unavailable
- `4`: required metrics missing
- `5`: internal error

## 16. Configuration Schema

Complete parameterized example:

```yaml
app:
  name: yira
  environment: prod
  timezone: UTC

cluster:
  universe_name: prod-yugabyte
  universe_uuid: null
  yba_url: "https://yba.example.com"
  prometheus_url: "http://yba-host:9090"
  prometheus_auth:
    type: none
  labels:
    universe: prod-yugabyte

window:
  incident_start: "2026-05-26T10:00:00Z"
  incident_end: "2026-05-26T10:30:00Z"
  step: "30s"
  rate_window: "2m"
  baseline:
    before: "30m"
  recovery:
    after: "15m"

topology:
  expected_node_count: 10
  replication_factor: 3
  placement_pattern: "4+4+2"
  regions:
    - name: region-a
      expected_nodes: 4
    - name: region-b
      expected_nodes: 4
    - name: region-c
      expected_nodes: 2
  node_label_mapping:
    node: "exported_instance"
    region: "region"
    az: "az"

data_sources:
  prometheus:
    enabled: true
    max_concurrency: 8
    timeout: "30s"
    retries: 3
  logs:
    enabled: true
    source_type: local
    path: "./logs"
  ysql_snapshots:
    enabled: false
  workload:
    enabled: true
    spark_metrics_file: "./spark_metrics.json"
    api_metrics_file: "./api_metrics.json"

detection:
  min_duration: "60s"
  zscore_warning: 2.5
  zscore_critical: 4.0
  default_warning_multiplier: 3
  default_critical_multiplier: 10

correlation:
  bucket: "30s"
  default_max_lag: "2m"
  cause_must_precede_symptom: true
  entity_match_required: false

scoring:
  confidence_high: 0.80
  confidence_medium: 0.60
  confidence_low: 0.40

output:
  directory: "./reports"
  formats: ["markdown", "json"]
  include_raw_samples: false
  include_promql: true
  redact:
    query_text: true
    hostnames: false
```

## 17. Implementation Architecture

```text
Config Loader
  -> validates schema and loads metric/rule packs

Discovery Layer
  -> discovers metrics, labels, nodes, regions, services

Collectors
  -> Prometheus Collector
  -> Log Collector
  -> SQL Snapshot Collector
  -> Workload Collector

Normalizer
  -> converts all source data into bucketed signals/events

Signal Engine
  -> threshold detection
  -> baseline anomaly detection
  -> skew detection
  -> duration detection

Correlation Engine
  -> time/entity/causal correlation

RCA Engine
  -> weighted scoring
  -> competing hypothesis ranking

Report Generator
  -> Markdown
  -> JSON
  -> optional HTML/dashboard later
```

## 18. Recommended Technology Stack

Initial CLI:

- Python 3.11+
- `pydantic` for config schema
- `httpx` for Prometheus/YBA API
- `pandas` or `polars` for time-series alignment
- `PyYAML` for config
- `jinja2` for reports
- `typer` or `click` for CLI
- `pytest` for unit tests

Future service:

- FastAPI
- background job queue
- object storage for reports
- optional React/Grafana-style dashboard

## 19. Security Requirements

- Prometheus/YBA credentials must come from environment variables, secret files, or secret managers.
- Reports must support redaction of hostnames, IPs, query text, usernames, and literals.
- SQL snapshots must use read-only credentials.
- Logs may contain sensitive SQL literals; default behavior must redact known sensitive patterns.
- The analyzer must never execute write SQL.
- The analyzer must not call remediation APIs in v1.

## 20. Reliability Requirements

- Partial data must produce partial analysis, not total failure, unless required sources are unavailable.
- Missing metric aliases must be reported clearly.
- Prometheus query failures must be retried with backoff.
- Large responses must be chunked by time range when needed.
- All report evidence must include enough metadata to reproduce the PromQL query.

## 21. Testing Strategy

### Unit Tests

- config validation
- PromQL template rendering
- signal severity classification
- baseline anomaly detection
- correlation scoring
- missing metric handling
- log regex parsing

### Integration Tests

- mocked Prometheus API
- sample YBA metric payloads
- sample logs for RPC timeout, Raft election, compaction, disk stall
- sample Spark/API workload files

### Golden Incident Tests

Create replayable fixtures:

- replication lag incident
- storage stall incident
- RPC queue saturation incident
- network retransmit incident
- hot tablet incident
- transaction conflict incident
- Spark write pressure incident
- low-evidence/no-root-cause incident

### Accuracy Measurement

```yaml
success_metrics:
  follower_lag_detection_recall: 1.0
  known_incident_top1_accuracy: 0.80
  known_incident_top3_accuracy: 0.95
  median_analysis_runtime_30m_window: "<120s"
  false_high_confidence_rate: "<5%"
```

## 22. MVP Scope

### MVP 1: Offline CLI Analyzer

- YAML config
- Prometheus query_range collector
- static metric registry
- baseline + static threshold signal detection
- rule-based correlation
- weighted RCA scoring
- Markdown and JSON reports
- missing metric report

### MVP 2: Logs and Workload Correlation

- log ingestion
- Spark/API metric file ingestion
- log timeline in report
- workload-pressure root cause scoring

### MVP 3: YSQL Snapshot Support

- bounded read-only SQL snapshots
- query fingerprint summary
- lock/conflict/terminated query evidence

### MVP 4: Continuous Mode

- scheduled runs
- alert webhook input
- report archive
- trend comparison

## 23. Future Enhancements

- Tablet-level and table-level RCA when safe metric sources are available.
- Integration with YBA support bundles.
- Grafana dashboard export.
- ML-assisted anomaly ranking.
- Causal graph visualization.
- Automated postmortem draft generation.
- Real-time alert enrichment.
- Runbook recommendations mapped to detected root cause.
- Historical incident learning and threshold tuning.

## 24. Key Open Questions

- Which YBA/YugabyteDB version is used?
- Are node-level metrics available in YBA Prometheus for CPU, iowait, disk, and TCP retransmits?
- Can the analyzer access YBA universe metadata APIs?
- Are Spark metrics available through Prometheus, logs, event history, or files?
- Do API services expose latency metrics with labels for endpoint/query class/region?
- Is read latency observed at application level, YSQL level, or both?
- Are queries using follower reads, bounded staleness, read replicas, or leader-only reads?
- Is the 2-node region serving reads directly?
- Are table placement policies, tablespaces, or leader preferences configured?

## 25. Acceptance Criteria

- Given a 30-minute incident window, YIRA produces Markdown and JSON reports.
- Reports show symptom metrics, root cause ranking, evidence, affected nodes/regions, missing evidence, and recommended next diagnostics.
- The tool can run with only YBA Prometheus for core analysis.
- Thresholds, metric names, root cause weights, log patterns, topology, and correlation lags are configurable.
- Missing optional metrics reduce confidence but do not fail the run.
- The same config model supports the current `4 + 4 + 2` universe and other future topologies.

