from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .analyzer import analyze
from .config import build_window, load_config
from .prometheus import PrometheusClient, PrometheusError
from .reports import render_markdown, write_reports


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="yira", description="YugabyteDB YSQL Incident RCA analyzer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze an incident window")
    analyze_parser.add_argument("--config", required=True, help="Path to yira YAML config")

    validate_parser = subparsers.add_parser("validate-config", help="Validate config and window")
    validate_parser.add_argument("--config", required=True, help="Path to yira YAML config")

    discover_parser = subparsers.add_parser("discover", help="Discover Prometheus metric names")
    discover_parser.add_argument("--config", required=True, help="Path to yira YAML config")

    list_parser = subparsers.add_parser("list-metrics", help="List Prometheus metric names")
    list_parser.add_argument("--prometheus-url", required=True, help="Prometheus base URL")

    explain_parser = subparsers.add_parser("explain", help="Render a JSON report as Markdown")
    explain_parser.add_argument("--report", required=True, help="Path to JSON report")

    args = parser.parse_args(argv)

    try:
        if args.command == "analyze":
            config = load_config(args.config)
            report = analyze(config)
            paths = write_reports(config, report)
            primary = report.primary_root_cause
            print(f"Analysis complete: {primary.category if primary else 'undetermined'}")
            print(f"Confidence: {primary.confidence_band if primary else 'insufficient_evidence'}")
            for kind, path in paths.items():
                print(f"{kind}: {path}")
            if primary and primary.score < primary.threshold:
                raise SystemExit(1)
        elif args.command == "validate-config":
            config = load_config(args.config)
            window = build_window(config)
            print("Config valid")
            print(f"Incident window: {window.incident_start.isoformat()} to {window.incident_end.isoformat()}")
            print(f"Query window: {window.query_start.isoformat()} to {window.query_end.isoformat()}")
            print(f"Metrics configured: {len(config.get('metrics', {}))}")
        elif args.command == "discover":
            config = load_config(args.config)
            prometheus_url = config.get("cluster", {}).get("prometheus_url")
            if not prometheus_url:
                raise ValueError("cluster.prometheus_url is required")
            client = PrometheusClient(prometheus_url)
            names = client.list_metric_names()
            configured = set(config.get("metrics", {}))
            print(f"Discovered metrics: {len(names)}")
            print(f"Configured logical metrics: {len(configured)}")
            for name in names[:200]:
                print(name)
        elif args.command == "list-metrics":
            client = PrometheusClient(args.prometheus_url)
            for name in client.list_metric_names():
                print(name)
        elif args.command == "explain":
            # The JSON report already contains rendered RCA data. Keep this command
            # dependency-free by printing a concise summary instead of rehydrating dataclasses.
            payload = json.loads(Path(args.report).read_text(encoding="utf-8"))
            print(f"# YIRA Incident Report: {payload.get('incident_id', 'unknown')}")
            primary = (payload.get("root_causes") or [{}])[0]
            print()
            print(f"- Primary root cause: `{primary.get('category', 'undetermined')}`")
            print(f"- Confidence: `{primary.get('confidence_band', 'insufficient_evidence')}` ({primary.get('score', 0):.2f})")
            print(f"- Signals: `{len(payload.get('signals', []))}`")
            print(f"- Missing metrics: `{len(payload.get('missing_metrics', []))}`")
    except (ValueError, PrometheusError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


__all__ = ["main", "render_markdown"]
