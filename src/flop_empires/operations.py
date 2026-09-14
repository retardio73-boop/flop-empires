from __future__ import annotations

from enum import StrEnum
from typing import Any


class AlertLevel(StrEnum):
    INFO="INFO"
    REVIEW="REVIEW"
    PAUSE_RECOMMENDED="PAUSE_RECOMMENDED"


def evaluate_monitoring(metrics: dict[str,int],thresholds: dict[str,dict[str,Any]])->dict[str,str]:
    """Classify observations only; this function cannot mutate rules or pause a Season."""
    result={}
    for name,rule in sorted(thresholds.items()):
        value=metrics.get(name,0)
        if not isinstance(value,int) or isinstance(value,bool): raise ValueError(f"invalid metric {name}")
        comparison=rule.get("comparison","gte")
        if comparison not in {"gte","lte"}: raise ValueError(f"invalid comparison for {name}")
        review,pause=rule.get("review"),rule.get("pause_recommended")
        if not all(isinstance(x,int) and not isinstance(x,bool) for x in (review,pause)):
            raise ValueError(f"invalid thresholds for {name}")
        crossed=lambda boundary: value>=boundary if comparison=="gte" else value<=boundary
        result[name]=(AlertLevel.PAUSE_RECOMMENDED if crossed(pause) else
            AlertLevel.REVIEW if crossed(review) else AlertLevel.INFO)
    return result
