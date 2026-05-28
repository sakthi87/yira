from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


Severity = str


SEVERITY_RANK: dict[Severity, int] = {
    "normal": 0,
    "info": 1,
    "warning": 2,
    "critical": 3,
}


@dataclass(frozen=True)
class TimeWindow:
    incident_start: datetime
    incident_end: datetime
    query_start: datetime
    query_end: datetime
    step_seconds: int
    rate_window: str


@dataclass
class MetricPoint:
    timestamp: datetime
    value: float


@dataclass
class MetricSeries:
    metric: str
    labels: dict[str, str]
    unit: str
    query: str
    points: list[MetricPoint] = field(default_factory=list)


@dataclass
class Signal:
    name: str
    metric: str
    category: str
    severity: Severity
    score: float
    peak: float | None
    baseline: float | None
    multiplier: float | None
    first_seen: datetime | None
    last_seen: datetime | None
    unit: str
    categories: list[str] = field(default_factory=list)
    affected_nodes: list[str] = field(default_factory=list)
    affected_regions: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    reason: str = ""

    @property
    def duration_seconds(self) -> int:
        if not self.first_seen or not self.last_seen:
            return 0
        return max(int((self.last_seen - self.first_seen).total_seconds()), 0)


@dataclass
class CausalEdge:
    source: str
    target: str
    source_category: str
    target_category: str
    lag_seconds: int
    confidence: float
    reason: str


@dataclass
class CausalChain:
    name: str
    confidence: float
    signals: list[str]
    edges: list[CausalEdge]
    explanation: str


@dataclass
class LogEvent:
    timestamp: datetime | None
    rule: str
    severity: Severity
    categories: list[str]
    path: str
    line_number: int
    message: str


@dataclass
class RootCauseScore:
    category: str
    score: float
    confidence_band: str
    threshold: float
    evidence: list[str]
    signals: list[str]
    recommendations: list[str]


@dataclass
class AnalysisReport:
    incident_id: str
    generated_at: datetime
    window: TimeWindow
    symptom: dict[str, Any]
    root_causes: list[RootCauseScore]
    signals: list[Signal]
    causal_chains: list[CausalChain]
    log_events: list[LogEvent]
    missing_metrics: list[str]
    affected_nodes: list[str]
    affected_regions: list[str]
    recommendations: list[str]

    @property
    def primary_root_cause(self) -> RootCauseScore | None:
        return self.root_causes[0] if self.root_causes else None
