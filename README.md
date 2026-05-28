# YIRA: YugabyteDB YSQL Incident Root Cause Analyzer

YIRA is a CLI-first analyzer for YugabyteDB YSQL latency incidents. It queries YBA Prometheus for a configured incident window, detects anomalous signals, builds likely causal chains across YSQL/RPC/Raft/storage/resource/master/log layers, and writes Markdown plus JSON RCA reports.

## Install

```bash
# Create an isolated Python environment for YIRA.
python3 -m venv .venv

# Activate the local environment before installing or running commands.
source .venv/bin/activate

# Install YIRA and test dependencies in editable mode.
pip install -e ".[dev]"
```

## Quick Start

Edit `examples/yira.yaml` with your YBA Prometheus URL, universe label, incident window, and region names.

```bash
# Validate the YAML config, incident window, and metric count.
yira validate-config --config examples/yira.yaml

# Run RCA analysis and write Markdown/JSON reports.
yira analyze --config examples/yira.yaml
```

Reports are written to `./reports` by default.

## Useful Commands

```bash
# List raw metric names available from YBA Prometheus.
yira list-metrics --prometheus-url http://yba-host:9090

# Discover available metrics using the configured YBA Prometheus endpoint.
yira discover --config examples/yira.yaml

# Print a concise summary from a generated JSON report.
yira explain --report reports/<incident>.json
```

## Metric Coverage

YIRA uses two metric sources by default:

- A built-in YBA/YSQL catalog with explicit mappings for the listed YBA universe graph families: YSQL ops/latency, resource, tablet server, master server, master advanced, DocDB, WAL, Raft, RPC, catalog cache, memory/cache, and transaction metrics.
- Dynamic discovery from YBA Prometheus. It lists Prometheus metric names and queries every discovered non-YCQL metric up to `data_sources.prometheus.discovery.max_metrics`.
- Explicit consistency-wait and skew hooks for safe-time lag, read restarts, hot tablet load, and leader concentration.

YCQL/CQL metrics are excluded by default:

```yaml
data_sources:
  prometheus:
    collect_mode: configured_and_discovered
    discovery:
      enabled: true
      max_metrics: 2000
      exclude_regex: "(?i)(ycql|cql|cassandra|redis)"
```

Set `collect_mode: configured` if you want faster targeted analysis using only the configured catalog.

## How RCA Works

YIRA does not just list red metrics. It turns raw metrics into signals, orders those signals by time, checks entity overlap, and then scores root-cause hypotheses.

The report includes:

- `Root Cause Ranking`: weighted RCA categories such as RPC saturation, storage bottleneck, consistency wait latency, hotspot/leader skew, or Raft instability.
- `Likely Causal Chains`: timeline explanations such as `WAL latency -> consensus latency -> follower lag -> YSQL latency`.
- `Key Signals`: abnormal metrics with severity, duration, peak value, affected node/region, and reason.
- `Skew Findings`: nodes or regions that are much worse than the cluster median.
- `Missing Evidence`: configured metrics that returned no data for the time window.

YIRA currently models these causal patterns:

- write pressure -> WAL pressure -> Raft/consensus latency -> follower/safe-time lag -> YSQL latency
- RPC queue -> reactor delay -> queue timeout -> YSQL latency
- storage pressure -> WAL latency -> consensus latency -> follower lag -> YSQL latency
- network errors/skew -> consensus latency -> leader changes/follower lag -> YSQL latency
- catalog/tablet-location lookup pressure -> master latency -> YSQL latency
- cache/SST/LSM/DocDB read-path pressure -> YSQL latency
- transaction conflicts/read restarts -> YSQL latency
- hot tablet/node skew -> RPC/consensus pressure -> YSQL latency

## Validating Metrics Against Your YBA

YBA and YugabyteDB versions can expose different metric names or labels. Use this workflow to validate and tune the metric mappings before trusting RCA output.

```bash
# Confirm the YAML, incident window, and number of configured metrics are valid.
yira validate-config --config examples/yira.yaml

# List every raw metric name available in your YBA Prometheus.
yira list-metrics --prometheus-url http://yba-host:9090

# Run the full analysis for the configured time window.
yira analyze --config examples/yira.yaml
```

After `analyze` finishes, open the generated files in `reports/` and check the `missing_metrics` section. A missing metric means the configured PromQL returned no data for the time window.

To fix a missing metric:

1. Search the output from `yira list-metrics` for the closest real metric name.
2. Compare labels in YBA Prometheus if the metric exists but still returns no data.
3. Update only your environment in `examples/yira.yaml` under `metrics:` when the change is cluster-specific.
4. Update the built-in catalog in `yira/metric_catalog.py` when the mapping should be the default for everyone.
5. Rerun `yira analyze --config examples/yira.yaml` and confirm the metric no longer appears under `missing_metrics`.

Override any metric in YAML when your YBA/YugabyteDB version uses different names or labels:

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

Enable local log parsing:

```yaml
data_sources:
  logs:
    enabled: true
    path: ./logs
```

YIRA scans files under that directory and correlates deadline, Raft, and storage warnings with the incident window.

## Current Scope

This version includes metric collection, discovery, signal detection, node/region skew detection, temporal causal chains, RCA scoring, Markdown/JSON reports, and basic log correlation. It does not yet collect YSQL snapshots, YBA universe metadata, or cloud metrics directly, but the configuration and scoring model are built to accept those sources next.
