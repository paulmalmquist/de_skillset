from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]
Layer = Literal["source", "staging", "intermediate", "mart", "serving", "consumer"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False).encode()).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Finding(StrictModel):
    rule: str
    severity: Literal["block", "warn"]
    subject: str
    message: str
    remediation: str
    evidence: dict = Field(default_factory=dict)
    fingerprint: str = ""
    waived: bool = False
    exception_ticket: str | None = None

    def model_post_init(self, __context):
        if not self.fingerprint:
            self.fingerprint = digest({"rule": self.rule, "subject": self.subject, "evidence": self.evidence})


def finding(rule, subject, message, remediation, severity="block", **evidence):
    return Finding(rule=rule, severity=severity, subject=subject, message=message, remediation=remediation, evidence=evidence)


def report(kind, findings, **extra):
    blocked = sum(f.severity == "block" and not f.waived for f in findings)
    return {"kind": kind, "status": "blocked" if blocked else "review" if findings else "clear",
            "blocking": blocked, "findings": [f.model_dump() for f in findings], **extra}
