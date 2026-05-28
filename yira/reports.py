from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import AnalysisReport


def write_reports(config: dict[str, Any], report: AnalysisReport) -> dict[str, str]:
    output_dir = Path(config.get("output", {}).get("directory", "./reports"))
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = report.incident_id.replace(":", "-")
    paths: dict[str, str] = {}
    formats = config.get("output", {}).get("formats", ["markdown", "json"])
    if "json" in formats:
        path = output_dir / f"{stem}.json"
        path.write_text(json.dumps(to_jsonable(report), indent=2, sort_keys=True), encoding="utf-8")
        paths["json"] = str(path)
    if "markdown" in formats:
        path = output_dir / f"{stem}.md"
        path.write_text(render_markdown(report), encoding="utf-8")
        paths["markdown"] = str(path)
    return paths


def render_markdown(report: AnalysisReport) -> str:
    primary = report.primary_root_cause
    lines = [
        f"# YIRA Incident Report: {report.incident_id}",
        "",
        "## Summary",
        "",
        f"- Window: `{report.window.incident_start.isoformat()}` to `{report.window.incident_end.isoformat()}`",
        f"- Generated: `{report.generated_at.isoformat()}`",
        f"- Primary root cause: `{primary.category if primary else 'undetermined'}`",
        f"- Confidence: `{primary.confidence_band if primary else 'insufficient_evidence'}`"
        + (f" ({primary.score:.2f})" if primary else ""),
        "",
    ]
    if report.symptom:
        lines.extend(
            [
                "## Symptom",
                "",
                f"- Name: `{report.symptom.get('name', 'unknown')}`",
                f"- Peak: `{report.symptom.get('peak', 'n/a')}`",
                f"- Baseline: `{report.symptom.get('baseline', 'n/a')}`",
                "",
            ]
        )
    lines.extend(["## Root Cause Ranking", ""])
    if report.root_causes:
        for cause in report.root_causes:
            threshold_note = "meets threshold" if cause.score >= cause.threshold else "below threshold"
            lines.append(
                f"- `{cause.category}`: {cause.score:.2f} ({cause.confidence_band}, {threshold_note})"
            )
            for evidence in cause.evidence[:8]:
                lines.append(f"  - {evidence}")
    else:
        lines.append("- No root cause scored above zero. Check missing evidence and metric availability.")
    lines.append("")

    lines.extend(["## Key Signals", ""])
    if report.signals:
        for signal in report.signals[:20]:
            entity = ", ".join(signal.affected_nodes or signal.affected_regions or ["cluster"])
            lines.append(
                f"- `{signal.name}` {signal.severity} score={signal.score:.2f} "
                f"peak={format_value(signal.peak)}{signal.unit} entity={entity} reason={signal.reason}"
            )
    else:
        lines.append("- No warning or critical metric signals detected.")
    lines.append("")

    if report.log_events:
        lines.extend(["## Log Highlights", ""])
        for event in report.log_events[:20]:
            when = event.timestamp.isoformat() if event.timestamp else "unknown-time"
            lines.append(f"- `{event.rule}` {event.severity} {when} {event.path}:{event.line_number}")
            lines.append(f"  - {event.message}")
        lines.append("")

    lines.extend(["## Affected Entities", ""])
    lines.append(f"- Nodes: `{', '.join(report.affected_nodes) if report.affected_nodes else 'unknown'}`")
    lines.append(f"- Regions: `{', '.join(report.affected_regions) if report.affected_regions else 'unknown'}`")
    lines.append("")

    if report.missing_metrics:
        lines.extend(["## Missing Evidence", ""])
        for metric in report.missing_metrics:
            lines.append(f"- `{metric}` returned no data")
        lines.append("")

    lines.extend(["## Recommended Next Actions", ""])
    if report.recommendations:
        for item in report.recommendations:
            lines.append(f"- {item}")
    else:
        lines.append("- Add node-level metrics and workload metrics to improve RCA confidence.")
    lines.append("")
    return "\n".join(lines)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    return value


def format_value(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"
