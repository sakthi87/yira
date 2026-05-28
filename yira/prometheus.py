from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .config import parse_duration, render_template
from .metric_catalog import discovered_metric_definition, should_discover_metric
from .models import MetricPoint, MetricSeries, TimeWindow


class PrometheusError(RuntimeError):
    pass


class PrometheusClient:
    def __init__(self, base_url: str, timeout_seconds: int = 30, retries: int = 3) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.retries = retries

    def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step_seconds: int,
    ) -> list[dict[str, Any]]:
        params = urllib.parse.urlencode(
            {
                "query": query,
                "start": int(start.timestamp()),
                "end": int(end.timestamp()),
                "step": step_seconds,
            }
        )
        url = f"{self.base_url}/api/v1/query_range?{params}"
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(url, timeout=self.timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if payload.get("status") != "success":
                    raise PrometheusError(str(payload))
                return payload.get("data", {}).get("result", [])
            except Exception as exc:  # noqa: BLE001 - preserve original Prometheus failure detail.
                last_error = exc
                if attempt < self.retries:
                    time.sleep(min(2**attempt, 5))
        raise PrometheusError(f"Prometheus query failed after retries: {last_error}")

    def list_metric_names(self) -> list[str]:
        url = f"{self.base_url}/api/v1/label/__name__/values"
        with urllib.request.urlopen(url, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("status") != "success":
            raise PrometheusError(str(payload))
        return sorted(payload.get("data", []))


def collect_prometheus_metrics(
    config: dict[str, Any],
    window: TimeWindow,
) -> tuple[list[MetricSeries], list[str]]:
    prometheus_config = config.get("data_sources", {}).get("prometheus", {})
    if not prometheus_config.get("enabled", True):
        return [], []
    base_url = config.get("cluster", {}).get("prometheus_url")
    if not base_url:
        raise ValueError("cluster.prometheus_url is required when Prometheus is enabled")

    client = PrometheusClient(
        base_url=base_url,
        timeout_seconds=parse_duration(prometheus_config.get("timeout", "30s")),
        retries=int(prometheus_config.get("retries", 3)),
    )
    all_series: list[MetricSeries] = []
    missing: list[str] = []
    metric_defs = dict(config.get("metrics", {}))
    metric_defs.update(discover_metric_defs(config, window, client, metric_defs))

    for metric_name, metric_def in metric_defs.items():
        query_template = metric_def.get("query")
        if not query_template:
            continue
        query = render_template(query_template, config, window)
        results = client.query_range(query, window.query_start, window.query_end, window.step_seconds)
        if not results:
            if not metric_def.get("discovered", False):
                missing.append(metric_name)
            if metric_def.get("required", False):
                continue
        for result in results:
            labels = {str(k): str(v) for k, v in result.get("metric", {}).items()}
            points = [
                MetricPoint(
                    timestamp=datetime.fromtimestamp(float(ts), tz=timezone.utc),
                    value=float(value),
                )
                for ts, value in result.get("values", [])
                if value not in ("NaN", "+Inf", "-Inf")
            ]
            all_series.append(
                MetricSeries(
                    metric=metric_name,
                    labels=labels,
                    unit=metric_def.get("unit", ""),
                    query=query,
                    points=points,
                )
            )
    return all_series, missing


def discover_metric_defs(
    config: dict[str, Any],
    window: TimeWindow,
    client: PrometheusClient,
    configured_metrics: dict[str, Any],
) -> dict[str, Any]:
    prometheus_config = config.get("data_sources", {}).get("prometheus", {})
    discovery = prometheus_config.get("discovery", {})
    collect_mode = prometheus_config.get("collect_mode", "configured_and_discovered")
    if collect_mode == "configured" or not discovery.get("enabled", True):
        return {}

    include_pattern = discovery.get("include_regex") or ""
    exclude_pattern = discovery.get("exclude_regex") or ""
    include_re = re.compile(include_pattern) if include_pattern else None
    exclude_re = re.compile(exclude_pattern) if exclude_pattern else None
    max_metrics = int(discovery.get("max_metrics", 500))
    metric_filter = render_template("${metric_filter}", config, window)

    discovered: dict[str, Any] = {}
    for metric_name in client.list_metric_names():
        if len(discovered) >= max_metrics:
            break
        if metric_name in configured_metrics:
            continue
        if exclude_re and exclude_re.search(metric_name):
            continue
        if not should_discover_metric(metric_name, include_re):
            continue
        logical_name = f"discovered_{metric_name}"
        discovered[logical_name] = discovered_metric_definition(metric_name, metric_filter)
    return discovered
