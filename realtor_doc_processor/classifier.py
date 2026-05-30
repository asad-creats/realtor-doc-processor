"""
Document classification + field extraction via a cloud LLM.

Multi-step pipeline for accuracy on real, messy packets:

  Pass 1  SEGMENT  — one call per ~10-page chunk to find document boundaries
                     and types only. Overlapping results are merged.
  Pass 2  EXTRACT  — a separate, focused call PER document to pull its fields
                     from just that document's text. Focused beats one giant
                     multi-document prompt.
  Reconcile        — deal-level facts (address, price, parties, dates) are
                     taken preferentially from the main contract (RPA), then
                     filled in from other docs.
  Validate         — dates normalized to YYYY-MM-DD, numbers coerced, weak
                     segments flagged for review.

All LLM calls go through `llm.chat_json`, which retries and falls back across
providers. A failure in one chunk/doc is recorded in processing_notes, not
crashed.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Optional

from pathlib import Path

from . import llm
from .models import DocumentSegment, ExtractedFields, TransactionPacket
from .pdf_extract import PageContent, render_page_images
from .taxonomy import all_codes, get as get_doc_type, taxonomy_for_prompt

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama-3.3-70b-versatile"
VISION_MODEL_HINTS = ("vl", "minicpm-v", "llava", "vision", "scout", "maverick", "gpt-4o", "gemini")

PAGES_PER_CHUNK = 10
CHUNK_OVERLAP = 1
SEGMENT_TEXT_PER_PAGE = 1600     # chars of each page shown to the segmenter
EXTRACT_TEXT_BUDGET = 9000       # total chars of a document shown to the extractor


def is_vision_model(model: str) -> bool:
    low = (model or "").lower()
    return any(h in low for h in VISION_MODEL_HINTS)


# ─── Prompts ──────────────────────────────────────────────────────────────────

SEGMENT_SYSTEM = """You are an expert real estate transaction coordinator. You are shown a \
sequence of PDF pages (extracted text, possibly via OCR). Identify where each individual \
document starts and ends, and classify each one. Do NOT extract field values in this step.

Document taxonomy (use these EXACT codes):
{taxonomy}

Rules:
- A new document usually starts with a clear title/header or form number (e.g. "C.A.R. Form RPA").
- Counter offers and addenda are SEPARATE documents from the RPA, even when short.
- Multi-page reports (NHD, Inspection, HOA, Title) are ONE document even if internal pages vary.
- A blank page, fax cover, or separator is OTHER.
- If unsure of the type, still mark the boundary but lower the confidence — do not guess high.

Output ONLY valid JSON, no markdown, no prose:
{{"segments":[{{"start_page":<int>,"end_page":<int>,"doc_type_code":<code>,"confidence":<0..1>,"rationale":"<short>"}}]}}"""

EXTRACT_SYSTEM = """You are an expert real estate transaction coordinator extracting structured \
data from ONE document of type: {label} ({code}).
{description}

Extract ONLY what actually appears in the text below. Rules:
- Dates in ISO format YYYY-MM-DD.
- Prices/amounts as plain numbers (no $ or commas).
- Names as "First Last". List multiple buyers/sellers separately.
- If a field is not present in THIS document, use null (or [] for name lists). Do NOT guess.

Output ONLY valid JSON, no markdown, no prose, exactly this shape:
{{"property_address":<string|null>,"buyer_names":[],"seller_names":[],"purchase_price":<number|null>,\
"earnest_money":<number|null>,"contract_date":<"YYYY-MM-DD"|null>,"close_of_escrow_date":<"YYYY-MM-DD"|null>,\
"escrow_number":<string|null>,"mls_number":<string|null>,"listing_agent":<string|null>,"buyers_agent":<string|null>}}"""


# ─── Entry point ────────────────────────────────────────────────────────────────

def classify_packet(
    pages: list[PageContent],
    job_id: str,
    source_filename: str,
    api_key: Optional[str] = None,   # ignored (key comes from env)
    model: Optional[str] = None,
    host: Optional[str] = None,      # ignored (legacy)
    pdf_path: Optional[Path] = None,  # needed for the vision "fill blanks" pass
) -> TransactionPacket:
    model = llm.active_model(model or os.environ.get("AI_MODEL"))
    notes: list[str] = []

    logger.info("Pass 1 (segment): %d pages via %s (%s)",
                len(pages), llm.provider_name(), model)
    segments = _segment(pages, model, notes)
    logger.info("Pass 1 done: %d documents", len(segments))

    logger.info("Pass 2 (extract): %d documents", len(segments))
    for i, seg in enumerate(segments, 1):
        try:
            seg.fields = _extract_fields(seg, pages, model)
        except Exception as e:
            notes.append(f"Field extraction failed for document {i} "
                         f"({seg.doc_type_code}, p{seg.start_page}-{seg.end_page}): {e}")
            logger.warning("  doc %d extract failed: %s", i, e)

    # Pass 3 (vision): for documents missing key fields or that were scanned,
    # re-read the actual page images to fill in the blanks (e.g. dates).
    if pdf_path and _vision_enabled():
        for i, seg in enumerate(segments, 1):
            if not _needs_vision(seg, pages):
                continue
            try:
                vfields = _extract_fields_vision(seg, pdf_path, model)
                seg.fields = seg.fields.merge(vfields)  # text wins, vision fills gaps
                logger.info("  doc %d: vision fill applied", i)
            except Exception as e:
                notes.append(f"Vision extraction failed for document {i}: {e}")
                logger.warning("  doc %d vision failed: %s", i, e)

    tx_fields = _reconcile(segments)
    _validate_and_flag(segments, notes)

    return TransactionPacket(
        job_id=job_id,
        source_filename=source_filename,
        total_pages=len(pages),
        segments=segments,
        transaction_fields=tx_fields,
        processing_notes=notes,
    )


# ─── Pass 1: segmentation ───────────────────────────────────────────────────────

def _segment(pages: list[PageContent], model: str, notes: list[str]) -> list[DocumentSegment]:
    system = SEGMENT_SYSTEM.format(taxonomy=taxonomy_for_prompt())
    found: list[DocumentSegment] = []
    chunks = list(_make_chunks(pages, PAGES_PER_CHUNK, overlap=CHUNK_OVERLAP))

    for idx, chunk in enumerate(chunks, 1):
        lines = [
            f"Pages {chunk[0].page_num}-{chunk[-1].page_num} of the PDF. "
            f"Find document boundaries and types."
        ]
        for p in chunk:
            body = (p.text[:SEGMENT_TEXT_PER_PAGE] or "(no readable text on this page)")
            lines.append(f"\n--- PAGE {p.page_num} ({p.extraction_method}, {p.char_count} chars) ---\n{body}")
        try:
            raw = llm.chat_json(system, "\n".join(lines), model=model, max_tokens=2000)
            found.extend(_parse_segments(raw))
        except Exception as e:
            notes.append(f"Segmentation chunk {idx} failed: {e}")
            logger.warning("  segment chunk %d failed: %s", idx, e)

    merged = _merge_overlapping_segments(found)
    if not merged and pages:
        # Total failure → treat whole thing as one OTHER doc so the user still
        # gets a (flagged) result instead of nothing.
        merged = [DocumentSegment(start_page=1, end_page=len(pages),
                                  doc_type_code="OTHER", confidence=0.0,
                                  fields=ExtractedFields(),
                                  rationale="Could not segment; review manually.",
                                  needs_review=True)]
    return merged


def _parse_segments(raw_text: str) -> list[DocumentSegment]:
    parsed = _safe_json(raw_text)
    valid = set(all_codes())
    out: list[DocumentSegment] = []
    for s in parsed.get("segments", []) or []:
        try:
            start = int(s["start_page"])
            end = int(s["end_page"])
        except (KeyError, ValueError, TypeError):
            continue
        if end < start:
            start, end = end, start
        code = s.get("doc_type_code", "OTHER")
        if code not in valid:
            code = "OTHER"
        out.append(DocumentSegment(
            start_page=start, end_page=end, doc_type_code=code,
            confidence=float(s.get("confidence", 0.5) or 0.5),
            rationale=str(s.get("rationale", ""))[:300],
            fields=ExtractedFields(),
        ))
    return out


# ─── Pass 2: per-document field extraction ──────────────────────────────────────

def _extract_fields(seg: DocumentSegment, pages: list[PageContent], model: str) -> ExtractedFields:
    dt = get_doc_type(seg.doc_type_code)
    label = dt.label if dt else seg.doc_type_code
    desc = dt.description if dt else ""
    system = EXTRACT_SYSTEM.format(label=label, code=seg.doc_type_code, description=desc)

    # Gather this document's text (capped).
    buf, used = [], 0
    for p in pages:
        if seg.start_page <= p.page_num <= seg.end_page and p.text:
            remaining = EXTRACT_TEXT_BUDGET - used
            if remaining <= 0:
                break
            piece = p.text[:remaining]
            buf.append(f"--- PAGE {p.page_num} ---\n{piece}")
            used += len(piece)
    if not buf:
        return ExtractedFields()

    user = (f"Extract the fields for this {label} document from its text below.\n\n"
            + "\n".join(buf))
    raw = llm.chat_json(system, user, model=model, max_tokens=1200)
    return _parse_fields(raw)


# ─── Pass 3: vision fallback (fill missing fields from the page image) ───────────

def _vision_enabled() -> bool:
    return os.getenv("ENABLE_VISION", "1").strip().lower() not in ("0", "false", "no")


_CONTRACT_DOCS = {"RPA", "CounterOffer", "Addendum"}


def _needs_vision(seg: DocumentSegment, pages: list[PageContent]) -> bool:
    """Trigger vision when a document was scanned, or a contract is missing
    the fields most often stuck in form boxes (dates, price, address)."""
    in_range = [p for p in pages if seg.start_page <= p.page_num <= seg.end_page]
    scanned = any(p.extraction_method == "ocr" or p.char_count < 120 for p in in_range)
    f = seg.fields
    if seg.doc_type_code in _CONTRACT_DOCS:
        missing_core = not (f.contract_date and f.close_of_escrow_date
                            and f.purchase_price and f.property_address)
    else:
        missing_core = seg.doc_type_code in _PRIORITY and not f.property_address
    return scanned or missing_core


def _extract_fields_vision(seg: DocumentSegment, pdf_path: Path, model: str) -> ExtractedFields:
    dt = get_doc_type(seg.doc_type_code)
    label = dt.label if dt else seg.doc_type_code
    desc = dt.description if dt else ""
    system = EXTRACT_SYSTEM.format(label=label, code=seg.doc_type_code, description=desc)
    images = render_page_images(pdf_path, seg.start_page, seg.end_page)
    if not images:
        return ExtractedFields()
    user = (f"This is a {label} document ({len(images)} page image(s)). "
            f"Read the pages and extract the fields. Pay special attention to dates "
            f"and amounts that appear in form boxes, stamps, or near signatures.")
    raw = llm.vision_json(system, user, images)
    return _parse_fields(raw)


def _parse_fields(raw_text: str) -> ExtractedFields:
    d = _safe_json(raw_text)
    return ExtractedFields(
        property_address=_clean_str(d.get("property_address")),
        buyer_names=_clean_list(d.get("buyer_names")),
        seller_names=_clean_list(d.get("seller_names")),
        purchase_price=_coerce_number(d.get("purchase_price")),
        earnest_money=_coerce_number(d.get("earnest_money")),
        contract_date=_normalize_date(d.get("contract_date")),
        close_of_escrow_date=_normalize_date(d.get("close_of_escrow_date")),
        escrow_number=_clean_str(d.get("escrow_number")),
        mls_number=_clean_str(d.get("mls_number")),
        listing_agent=_clean_str(d.get("listing_agent")),
        buyers_agent=_clean_str(d.get("buyers_agent")),
    )


# ─── Reconcile + validate ───────────────────────────────────────────────────────

# Documents most trustworthy for deal-level facts, best first.
_PRIORITY = ["RPA", "CounterOffer", "EscrowInstructions", "ClosingDisclosure", "TDS"]


def _reconcile(segments: list[DocumentSegment]) -> ExtractedFields:
    """Build deal-level fields, preferring the main contract, then others."""
    def rank(seg: DocumentSegment) -> int:
        return _PRIORITY.index(seg.doc_type_code) if seg.doc_type_code in _PRIORITY else len(_PRIORITY)

    tx = ExtractedFields()
    for seg in sorted(segments, key=rank):
        tx = tx.merge(seg.fields)   # merge() keeps existing non-None, fills gaps
    tx.buyer_names = _dedupe_names(tx.buyer_names)
    tx.seller_names = _dedupe_names(tx.seller_names)
    return tx


def _dedupe_names(names: list[str]) -> list[str]:
    """Drop names whose words are fully contained in a longer name already kept.
    e.g. 'Chen' is removed when 'Marcus Chen' is present."""
    unique = list(dict.fromkeys(names))            # drop exact dups, keep order
    kept: list[str] = []
    for name in sorted(unique, key=lambda n: len(n.split()), reverse=True):
        words = set(name.lower().split())
        if any(words <= set(k.lower().split()) for k in kept):
            continue
        kept.append(name)
    return [n for n in unique if n in kept]         # original order


def _validate_and_flag(segments: list[DocumentSegment], notes: list[str]) -> None:
    for seg in segments:
        if seg.confidence < 0.75 or seg.doc_type_code == "OTHER":
            seg.needs_review = True
    if segments and not any(s.fields.property_address for s in segments):
        notes.append("No property address detected in any document — verify the packet.")


# ─── Helpers ────────────────────────────────────────────────────────────────────

def _make_chunks(pages: list[PageContent], size: int, overlap: int):
    i = 0
    while i < len(pages):
        end = min(i + size, len(pages))
        yield pages[i:end]
        if end >= len(pages):
            break
        i = end - overlap


def _merge_overlapping_segments(segments: list[DocumentSegment]) -> list[DocumentSegment]:
    if not segments:
        return []
    ordered = sorted(segments, key=lambda s: (s.start_page, s.end_page))
    merged = [ordered[0]]
    for seg in ordered[1:]:
        last = merged[-1]
        if seg.doc_type_code == last.doc_type_code and seg.start_page <= last.end_page + 1:
            last.end_page = max(last.end_page, seg.end_page)
            last.confidence = max(last.confidence, seg.confidence)
        else:
            merged.append(seg)
    return merged


def _safe_json(raw_text: str) -> dict:
    """Parse JSON, tolerating markdown fences and surrounding prose."""
    if not raw_text:
        return {}
    t = raw_text.strip()
    if t.startswith("```"):
        m = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
        t = (m.group(1) if m else re.sub(r"^```(?:json)?\s*", "", t)).strip()
    a, b = t.find("{"), t.rfind("}")
    if a >= 0 and b > a:
        t = t[a:b + 1]
    try:
        out = json.loads(t)
        return out if isinstance(out, dict) else {}
    except json.JSONDecodeError:
        return {}


def _clean_str(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s or None if s.lower() not in ("null", "n/a", "none", "") else None


def _clean_list(v) -> list[str]:
    if not v:
        return []
    if isinstance(v, str):
        v = [v]
    out = []
    for x in v:
        s = str(x).strip()
        if s and s.lower() not in ("null", "n/a", "none"):
            out.append(s)
    return out


def _coerce_number(v) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        cleaned = re.sub(r"[^\d.]", "", v)
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


_DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y",
                 "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%B %d %Y"]


def _normalize_date(v) -> Optional[str]:
    s = _clean_str(v)
    if not s:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s  # keep original if we can't parse it
