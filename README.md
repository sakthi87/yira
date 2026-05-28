# YIRA: YugabyteDB YSQL Incident Root Cause Analyzer

YIRA is a CLI-first analyzer for YugabyteDB YSQL latency incidents. It queries YBA Prometheus for a configured incident window, detects anomalous signals, correlates evidence across YSQL/RPC/Raft/storage/resource/master/log layers, and writes Markdown plus JSON RCA reports.

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

This is MVP 1 plus basic log correlation. It does not yet collect YSQL snapshots, YBA universe metadata, or cloud metrics directly, but the configuration and scoring model are built to accept those sources next.
