"""
Data models for the document processing pipeline.

Everything that crosses a module boundary uses these types. This makes
the manual-processing version and the future automated version use the
exact same data shapes — when you flip the switch, nothing else changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Optional
import json


@dataclass
class ExtractedFields:
    """
    Transaction-level fields we try to pull out of every document.

    Not every doc will have all of these (a wire instruction won't have
    a purchase price). Missing fields are None — never empty strings.
    """
    property_address: Optional[str] = None
    buyer_names: list[str] = field(default_factory=list)
    seller_names: list[str] = field(default_factory=list)
    purchase_price: Optional[float] = None
    earnest_money: Optional[float] = None
    contract_date: Optional[str] = None         # ISO format YYYY-MM-DD
    close_of_escrow_date: Optional[str] = None  # ISO format YYYY-MM-DD
    escrow_number: Optional[str] = None
    mls_number: Optional[str] = None
    listing_agent: Optional[str] = None
    buyers_agent: Optional[str] = None

    def merge(self, other: "ExtractedFields") -> "ExtractedFields":
        """
        Merge another ExtractedFields into this one, preferring non-None values.
        Used to build a transaction-level summary from many per-doc extractions.
        """
        result = ExtractedFields()
        for f in self.__dataclass_fields__:
            mine = getattr(self, f)
            theirs = getattr(other, f)
            if isinstance(mine, list):
                # Union the lists, preserving order, deduping
                seen = set()
                combined = []
                for item in mine + theirs:
                    if item and item not in seen:
                        seen.add(item)
                        combined.append(item)
                setattr(result, f, combined)
            else:
                setattr(result, f, mine if mine is not None else theirs)
        return result


@dataclass
class DocumentSegment:
    """
    A single classified document within a (possibly combined) PDF.

    Page numbers are 1-indexed and inclusive — page 1 to page 5 means
    a 5-page document.
    """
    start_page: int
    end_page: int
    doc_type_code: str       # one of taxonomy.all_codes()
    confidence: float        # 0.0 to 1.0
    fields: ExtractedFields
    rationale: str = ""      # why the AI thinks this is what it is
    needs_review: bool = False  # set by review logic

    @property
    def page_count(self) -> int:
        return self.end_page - self.start_page + 1


@dataclass
class TransactionPacket:
    """
    The result of processing one upload from one user.

    Contains everything needed to: (a) split the original PDF into
    properly named files, (b) generate a transaction summary, (c) push
    to Canva or another template renderer.
    """
    job_id: str
    source_filename: str
    total_pages: int
    segments: list[DocumentSegment]
    transaction_fields: ExtractedFields  # merged across all segments
    processing_notes: list[str] = field(default_factory=list)

    def low_confidence_segments(self, threshold: float = 0.75) -> list[DocumentSegment]:
        """Segments that should be flagged for human review."""
        return [s for s in self.segments if s.confidence < threshold or s.needs_review]

    def to_json(self) -> str:
        """Serialize for storage / sending back to the web frontend."""
        return json.dumps(asdict(self), indent=2, default=str)

    @classmethod
    def from_json(cls, data: str) -> "TransactionPacket":
        d = json.loads(data)
        d["transaction_fields"] = ExtractedFields(**d["transaction_fields"])
        d["segments"] = [
            DocumentSegment(
                **{**s, "fields": ExtractedFields(**s["fields"])}
            )
            for s in d["segments"]
        ]
        return cls(**d)
