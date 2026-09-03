"""Pure document contracts for the v8 discovery and evidence indexes."""

from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class DiscoveryDocument:
    product_id: str
    text: str
    payload: dict


@dataclass(frozen=True)
class EvidenceDocument:
    evidence_id: str
    product_id: str
    source_type: str
    text: str
    payload: dict
