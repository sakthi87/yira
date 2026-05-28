# YIRA: YugabyteDB YSQL Incident Reasoning Analyzer

YIRA is a CLI-based distributed-system incident reasoning engine for YugabyteDB YSQL latency analysis.

Rather than only surfacing abnormal metrics, YIRA reconstructs likely incident propagation chains across YSQL execution, RPC processing, Raft replication, storage-engine behavior, cluster coordination, and infrastructure resources.

Given a configured incident window, YIRA queries YBA Prometheus, detects abnormal signals, correlates behavior across distributed-system layers, builds temporal causal chains, scores competing root-cause hypotheses, and generates human-readable Markdown plus machine-readable JSON RCA reports.

YIRA focuses on answering:

> What happened first, what propagated next, and what ultimately caused the observed YSQL latency impact?

Typical incident propagation chains include:

```text
write pressure
-> WAL latency
-> consensus latency
-> follower lag
-> safe-time lag
-> YSQL latency
```

```text
network instability
-> Raft retries
-> consensus delay
-> follower lag
-> read consistency wait
-> YSQL latency
```

```text
hot tablet skew
-> RPC saturation
-> DocDB read pressure
-> intermittent SELECT latency
```

YIRA is designed for intermittent, transient, distributed-system failures that are difficult to explain using query plans or static dashboards alone.

## Core Capabilities

YIRA includes:

- Collection of about 90 built-in YBA/YSQL metrics
- Dynamic discovery of additional non-YCQL metrics from YBA Prometheus
- Temporal causal-chain reconstruction
- RCA scoring across distributed-system layers
- Node/region skew detection
- Safe-time and consistency-wait analysis
- Hot tablet and leader-skew detection
- Markdown and JSON report generation
- Missing-metric reporting for YBA-version compatibility
- Optional TServer/Master log correlation

Covered signal domains include:

- YSQL latency and operations
- TServer metrics
- Master metrics
- DocDB / RocksDB
- WAL and compaction
- Raft / consensus
- RPC queues and reactor delays
- CPU, memory, disk, network
- cache and SSTables
- transaction conflicts and read restarts
- clock skew and replication lag

YCQL/CQL metrics are excluded by default.

## Why YIRA Exists

Distributed YugabyteDB latency incidents are rarely caused by the SQL query itself.

Many intermittent latency spikes originate from:

- replication delays
- RPC saturation
- Raft instability
- consistency waits
- WAL pressure
- hotspot skew
- storage-engine contention
- transient infrastructure imbalance

Traditional dashboards expose metrics but rarely explain causal propagation across distributed-system layers.

YIRA focuses on reconstructing likely incident timelines and causal reasoning.

Instead of only reporting:

```text
follower lag high
consensus latency high
ysql latency high
```

YIRA attempts to explain:

```text
Spark write pressure increased first.

This increased WAL throughput and consensus latency.

Replication acknowledgements slowed down,
causing follower lag and delayed safe-time propagation.

Some YSQL SELECT requests then waited on consistency resolution,
causing intermittent 10-second latency spikes.
```

## Install

```bash
# Create isolated Python environment.
python3 -m venv .venv

# Activate environment.
source .venv/bin/activate

# Install YIRA in editable mode.
pip install -e ".[dev]"
```

## Quick Start

Edit `examples/yira.yaml` with:

- YBA Prometheus URL
- universe label
- incident time window
- topology/region information

Run:

```bash
# Validate YAML configuration and incident window.
yira validate-config --config examples/yira.yaml

# Run RCA analysis.
yira analyze --config examples/yira.yaml
```

Reports are written to:

```text
./reports
```

## Useful Commands

```bash
# List raw metric names available from YBA Prometheus.
yira list-metrics --prometheus-url http://yba-host:9090

# Discover metrics using configured YBA Prometheus endpoint.
yira discover --config examples/yira.yaml

# Run RCA analysis.
yira analyze --config examples/yira.yaml

# Print concise explanation from generated JSON report.
yira explain --report reports/<incident>.json
```

## Example RCA Output

Example incident timeline:

```text
10:14:02  Spark write throughput increased
10:14:05  WAL throughput increased
10:14:08  Consensus latency increased
10:14:11  Follower lag reached 5816ms
10:14:14  Safe-time lag increased
10:14:18  YSQL SELECT latency exceeded 10s
```

Example RCA explanation:

```text
Write amplification caused Raft replication delay,
which delayed safe-time propagation and impacted read latency.
```

## How RCA Works

YIRA does not just list abnormal metrics.

It converts raw metrics into signals, aligns those signals in time, detects node/region skew, correlates affected entities, builds temporal propagation chains, and scores competing root-cause hypotheses.

The analysis pipeline is:

```text
Prometheus metrics
-> signal detection
-> temporal correlation
-> causal-chain reconstruction
-> RCA scoring
-> Markdown/JSON report generation
```

## RCA Categories

YIRA currently scores RCA categories such as:

- RPC saturation
- storage bottleneck
- replication delay
- consistency-wait latency
- network instability
- hotspot / leader skew
- DocDB read-path pressure
- Raft instability
- master pressure
- CPU/thread saturation
- memory/cache pressure
- transaction contention

## Causal Patterns Modeled

YIRA currently models distributed-system propagation patterns including:

```text
write pressure
-> WAL pressure
-> Raft latency
-> follower lag
-> safe-time lag
-> YSQL latency
```

```text
RPC queue
-> reactor delay
-> request timeout
-> YSQL latency
```

```text
storage pressure
-> WAL latency
-> consensus delay
-> follower lag
-> YSQL latency
```

```text
network instability
-> consensus retries
-> leader instability
-> follower lag
-> YSQL latency
```

```text
cache/SST/LSM/DocDB pressure
-> read amplification
-> YSQL latency
```

```text
transaction conflicts/read restarts
-> consistency wait
-> YSQL latency
```

```text
hot tablet skew
-> RPC saturation
-> consensus pressure
-> intermittent latency
```

## Metric Coverage

YIRA uses two metric sources by default:

### 1. Built-In Catalog

A curated YBA/YSQL metric catalog covering:

- YSQL operations and latency
- TServer metrics
- Master metrics
- WAL
- Raft
- RPC
- DocDB
- RocksDB
- cache and SSTables
- transaction metrics
- resource metrics

Implemented in:

```text
yira/metric_catalog.py
```

### 2. Dynamic Discovery

YIRA can dynamically discover additional metrics directly from YBA Prometheus.

Example:

```yaml
data_sources:
  prometheus:
    collect_mode: configured_and_discovered
    discovery:
      enabled: true
      max_metrics: 2000
      exclude_regex: "(?i)(ycql|cql|cassandra|redis)"
```

Set:

```yaml
collect_mode: configured
```

for faster targeted analysis using only curated metrics.

## Validating Metrics Against Your YBA Version

YBA and YugabyteDB versions may expose different metric names or labels.

Recommended workflow:

```bash
# Validate configuration.
yira validate-config --config examples/yira.yaml

# List all available Prometheus metrics.
yira list-metrics --prometheus-url http://yba-host:9090

# Run analysis.
yira analyze --config examples/yira.yaml
```

After analysis completes, inspect:

```text
reports/<incident>.json
```

and review:

```text
missing_metrics
```

A missing metric indicates the configured PromQL returned no data for the selected window.

To resolve:

1. Search `list-metrics` output for equivalent metric names.
2. Validate labels in YBA Prometheus.
3. Override cluster-specific mappings in `examples/yira.yaml`.
4. Update shared defaults in `yira/metric_catalog.py`.
5. Rerun analysis.

Example metric override:

```yaml
cluster:
  metric_filter: 'node_prefix="$universe"'

metrics:
  follower_lag_ms:
    unit: ms
    query: 'max by (exported_instance, region) (your_follower_lag_metric{${metric_filter}})'
    required: false
    categories: ["follower_lag_spike", "replication"]
    severity:
      warning: {gt: 1000}
      critical: {gt: 5000}
```

## Log Correlation

Optional local log correlation:

```yaml
data_sources:
  logs:
    enabled: true
    path: ./logs
```

YIRA scans log files under the configured directory and correlates:

- deadline exceeded warnings
- Raft instability
- consensus retries
- tablet movement
- storage warnings
- RPC failures

with the configured incident window.

## Repository Structure

```text
examples/yira.yaml          Runtime configuration
yira/metric_catalog.py      Built-in metric mappings
yira/prometheus.py          Prometheus collection layer
yira/signals.py             Signal detection engine
yira/causal.py              Temporal causal-chain logic
yira/rca.py                 RCA scoring engine
yira/reports.py             Markdown/JSON report generation
```

## Current Scope

Current capabilities include:

- metric collection
- metric discovery
- anomaly detection
- skew detection
- temporal causal chains
- RCA scoring
- report generation
- optional log correlation

YIRA does not yet collect:

- YSQL snapshots
- YBA universe metadata
- cloud-provider metrics
- tracing spans

However, the architecture and scoring model are designed to integrate those sources later.

## Long-Term Direction

YIRA is evolving toward:

- temporal causal graphs
- hotspot topology analysis
- real-time streaming RCA
- distributed incident fingerprinting
- historical incident similarity detection
- Grafana visualization
- automated mitigation recommendations

The long-term goal is to move from:

```text
metric monitoring
```

to:

```text
distributed incident reasoning
```
