from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import LogEvent, TimeWindow


TIMESTAMP_PATTERNS = [
    re.compile(r"(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)"),
    re.compile(r"(?P<ts>[IWEF]\d{4} \d{2}:\d{2}:\d{2}\.\d+)"),
]


def collect_log_events(config: dict[str, Any], window: TimeWindow) -> list[LogEvent]:
    source_config = config.get("data_sources", {}).get("logs", {})
    if not source_config.get("enabled", False):
        return []
    root = Path(source_config.get("path", "./logs"))
    if not root.exists():
        return []

    patterns = compile_patterns(config)
    events: list[LogEvent] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line_number, line in enumerate(handle, start=1):
                    event_time = parse_log_timestamp(line)
                    if event_time and not (window.query_start <= event_time <= window.query_end):
                        continue
                    for name, rule in patterns.items():
                        if rule["regex"].search(line):
                            events.append(
                                LogEvent(
                                    timestamp=event_time,
                                    rule=name,
                                    severity=rule["severity"],
                                    categories=rule["categories"],
                                    path=str(path),
                                    line_number=line_number,
                                    message=line.strip()[:500],
                                )
                            )
        except OSError:
            continue
    return events


def compile_patterns(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    defaults = {
        "log_deadline_expired": {
            "severity": "critical",
            "regex": r"(?i)(deadline expired|timed out|timeout|service unavailable)",
            "categories": ["rpc", "latency"],
        },
        "log_raft_warnings": {
            "severity": "warning",
            "regex": r"(?i)(election|leader changed|RequestConsensusVotes|remote bootstrap|StartRemoteBootstrap)",
            "categories": ["raft", "replication"],
        },
        "log_storage_warnings": {
            "severity": "warning",
            "regex": r"(?i)(rocksdb|compaction|flush|fsync|stall)",
            "categories": ["storage"],
        },
    }
    configured = config.get("logs", {}).get("patterns", {})
    rules = {**defaults, **configured}
    return {
        name: {
            "severity": rule.get("severity", "warning"),
            "categories": rule.get("categories", []),
            "regex": re.compile(rule["regex"]),
        }
        for name, rule in rules.items()
        if rule.get("regex")
    }


def parse_log_timestamp(line: str) -> datetime | None:
    for pattern in TIMESTAMP_PATTERNS:
        match = pattern.search(line)
        if not match:
            continue
        raw = match.group("ts")
        if raw[0] in "IWEF":
            year = datetime.now(tz=timezone.utc).year
            raw = f"{year}{raw[1:]}"
            try:
                return datetime.strptime(raw, "%Y%m%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None
