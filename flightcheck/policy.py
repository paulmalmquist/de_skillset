from __future__ import annotations

import fnmatch
from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import Field

from .common import Layer, StrictModel, digest, finding


class ExceptionRule(StrictModel):
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    owner: str = Field(min_length=3)
    reviewer: str = Field(min_length=3)
    ticket: str = Field(min_length=3)
    reason: str = Field(min_length=15)
    expires_at: datetime


class PublishedContract(StrictModel):
    owner: str = Field(min_length=3)
    contract_id: str = Field(min_length=3)
    lineage_reviewed: bool
    expires_at: datetime


class Policy(StrictModel):
    version: str = "1"
    dialect: str = "bigquery"
    relation_layers: dict[str, Layer] = Field(default_factory=lambda: {
        "*.raw.*": "source", "*.staging.*": "staging", "*.intermediate.*": "intermediate",
        "*.mart.*": "mart", "*.serving.*": "serving", "raw.*": "source",
        "staging.*": "staging", "intermediate.*": "intermediate", "mart.*": "mart", "serving.*": "serving"})
    allowed_dependencies: dict[str, list[Layer]] = Field(default_factory=lambda: {
        "source": [], "staging": ["source"], "intermediate": ["staging", "intermediate"],
        "mart": ["staging", "intermediate", "mart"], "serving": ["mart", "serving"],
        "consumer": ["mart", "serving"]})
    max_freshness_hours: float = Field(default=24, gt=0)
    max_evidence_age_hours: float = Field(default=4, gt=0)
    exceptions: list[ExceptionRule] = Field(default_factory=list)
    published_contracts: dict[str, PublishedContract] = Field(default_factory=dict)

    def publication_registered(self, relation, now=None):
        entry = self.published_contracts.get(relation.lower())
        now = now or datetime.now(timezone.utc)
        return bool(entry and entry.lineage_reviewed and entry.expires_at.tzinfo
                    and entry.expires_at > now)

    def classify(self, relation: str) -> str:
        matches = {layer for pattern, layer in self.relation_layers.items()
                   if fnmatch.fnmatchcase(relation.lower(), pattern.lower())}
        return next(iter(matches)) if len(matches) == 1 else "unknown"

    @property
    def hash(self):
        return digest(self.model_dump(mode="json"))


def load_policy(path: str | Path | None = None) -> Policy:
    return Policy.model_validate(yaml.safe_load(Path(path).read_text())) if path else Policy()


def apply_exceptions(findings, policy: Policy, now=None):
    now = now or datetime.now(timezone.utc)
    extra = []
    nonwaivable = {"SQL_PARSE", "SQL_UNCOMPILED", "SQL_READ_ONLY", "MANIFEST_FORMAT", "LINEAGE_INCOMPLETE", "LINEAGE_CYCLE", "ROUTINE_COVERAGE", "PUBLISHED_CONTRACT", "SQL_COVERAGE", "RELATION_IDENTITY", "MODEL_CONTRACT", "MODEL_TESTS"}
    for exception in policy.exceptions:
        expiry = exception.expires_at
        if expiry.tzinfo is None or expiry <= now or exception.owner == exception.reviewer:
            extra.append(finding("EXCEPTION_INVALID", exception.ticket, "Exception expired, lacks a timezone, or is self-reviewed.", "Obtain independent review with an explicit UTC expiration."))
            continue
        for f in findings:
            if f.fingerprint == exception.fingerprint and f.rule not in nonwaivable:
                f.waived = True
                f.exception_ticket = exception.ticket
    return findings + extra
