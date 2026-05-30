"""
Document classification + field extraction via a cloud LLM.

Calls a hosted, OpenAI-compatible provider (Groq by default) over HTTPS
through `realtor_doc_processor.llm` — the same approach as the TC Command
Center backend. No local GPU, no Ollama daemon, deployable anywhere.

Configure the provider/model with env vars (see llm.py):
    AI_PROVIDER (default groq), AI_MODEL, GROQ_API_KEY, ...

Design:
1. Pages are sent in CHUNKS of ~10 with 1-page overlap so a document spanning
   a chunk boundary still gets seen whole.
2. Each page goes in as TEXT (extracted by pdfplumber, OCR fallback for scans).
   The default cloud models are text-only — real estate packets are text-rich,
   so this classifies very well. Vision models can still be wired in later.
3. We ask for strict JSON. Models occasionally wrap output in markdown fences
   or trail explanations — the parser tolerates this.
4. Failed chunks are recorded in processing_notes; the pipeline does NOT crash
   on a single bad chunk.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

from . import llm
from .models import DocumentSegment, ExtractedFields, TransactionPacket
from .pdf_extract import PageContent
from .taxonomy import all_codes, taxonomy_for_prompt

logger = logging.getLogger(__name__)

# Default model id. Override with AI_MODEL env var or --model.
# This is resolved by llm.py per provider; kept here for messaging/back-compat.
DEFAULT_MODEL = "llama-3.3-70b-versatile"

# Substrings that mark a model as vision-capable. Kept for callers that want
# to know; the default cloud models are text-only and that's fine here.
VISION_MODEL_HINTS = ("vl", "minicpm-v", "llava", "vision", "scout", "maverick", "gpt-4o", "gemini")


def is_vision_model(model: str) -> bool:
    """True if the model name looks vision-capable (accepts images)."""
    low = (model or "").lower()
    return any(h in low for h in VISION_MODEL_HINTS)

PAGES_PER_CHUNK = 10
CHUNK_OVERLAP = 1

# Open-source models occasionally produce malformed JSON on the first try.
# We retry once with a stricter reminder.
MAX_PARSE_RETRIES = 1


SYSTEM_PROMPT = """You are an expert real estate transaction coordinator who has reviewed \
thousands of California residential transaction packets. Your job is to look at a \
sequence of PDF pages and identify where each individual document starts and ends, \
classify each one, and extract key transaction details.

You will be given pages with their text content and a thumbnail image. Use BOTH — \
the text tells you the content, the thumbnail tells you the layout, signatures, and \
any stamps or watermarks.

Document taxonomy (use these exact codes):
{taxonomy}

Rules for boundaries:
- A new document typically starts with a clear title page, header, or form number \
(e.g., "C.A.R. Form RPA").
- Counter offers and addenda often reference the original RPA — they are SEPARATE documents.
- Multi-page reports (NHD, Inspection, HOA) should be ONE document even if pages look different internally.
- If a single page is genuinely just a fax cover or blank separator, classify it as OTHER.
- If you're unsure, lower the confidence score — don't guess high.

Rules for field extraction:
- Pull fields from the document where they appear (purchase price from RPA, \
escrow # from escrow instructions, etc.).
- Use ISO date format YYYY-MM-DD for all dates.
- Strip dollar signs and commas from prices — return as numbers.
- For names, use "First Last" format. List multiple buyers/sellers separately.
- If a field isn't in the document, use null. Don't guess.

CRITICAL: Output ONLY valid JSON matching the exact schema below. Do not wrap in \
markdown fences. Do not add explanations before or after. Just the JSON object."""


RESPONSE_SCHEMA_HINT = """
{
  "segments": [
    {
      "start_page": <int, 1-indexed, relative to the FULL PDF>,
      "end_page": <int, 1-indexed, inclusive>,
      "doc_type_code": <one of the taxonomy codes>,
      "confidence": <float 0.0-1.0>,
      "rationale": <brief explanation of why you classified it this way>,
      "fields": {
        "property_address": <string or null>,
        "buyer_names": [<string>, ...],
        "seller_names": [<string>, ...],
        "purchase_price": <number or null>,
        "earnest_money": <number or null>,
        "contract_date": <"YYYY-MM-DD" or null>,
        "close_of_escrow_date": <"YYYY-MM-DD" or null>,
        "escrow_number": <string or null>,
        "mls_number": <string or null>,
        "listing_agent": <string or null>,
        "buyers_agent": <string or null>
      }
    }
  ]
}
"""


def classify_packet(
    pages: list[PageContent],
    job_id: str,
    source_filename: str,
    api_key: Optional[str] = None,  # kept for signature compatibility; ignored
    model: Optional[str] = None,
    host: Optional[str] = None,     # ignored (legacy Ollama arg)
) -> TransactionPacket:
    """
    Classify a full packet by chunking and merging results.

    Args:
        pages: list of PageContent from pdf_extract.extract_pdf
        job_id: identifier for this run (shows up in logs/output)
        source_filename: original PDF name (stored on the result)
        api_key: ignored (provider key comes from the environment).
        model: override the default model. Falls back to env AI_MODEL,
               then the provider default.
        host:  ignored. Retained so older callers don't break.
    """
    model = llm.active_model(model or os.environ.get("AI_MODEL"))

    all_segments: list[DocumentSegment] = []
    notes: list[str] = []

    chunks = list(_make_chunks(pages, PAGES_PER_CHUNK, overlap=CHUNK_OVERLAP))
    logger.info(
        "Classifying %d pages in %d chunks via %s (model=%s)",
        len(pages), len(chunks), llm.provider_name(), model,
    )

    for chunk_idx, chunk_pages in enumerate(chunks):
        logger.info(
            "  chunk %d/%d (pages %d-%d)",
            chunk_idx + 1, len(chunks),
            chunk_pages[0].page_num, chunk_pages[-1].page_num,
        )
        try:
            chunk_segments = _classify_chunk(model, chunk_pages)
            all_segments.extend(chunk_segments)
        except Exception as e:
            msg = f"Chunk {chunk_idx + 1} failed: {e}"
            logger.error(msg)
            notes.append(msg)

    merged = _merge_overlapping_segments(all_segments)

    tx_fields = ExtractedFields()
    for seg in merged:
        tx_fields = tx_fields.merge(seg.fields)

    for seg in merged:
        if seg.confidence < 0.75:
            seg.needs_review = True
        if seg.doc_type_code == "OTHER":
            seg.needs_review = True

    return TransactionPacket(
        job_id=job_id,
        source_filename=source_filename,
        total_pages=len(pages),
        segments=merged,
        transaction_fields=tx_fields,
        processing_notes=notes,
    )


# ---------- internals ----------

def _make_chunks(pages: list[PageContent], size: int, overlap: int):
    """Yield overlapping chunks of pages."""
    i = 0
    while i < len(pages):
        end = min(i + size, len(pages))
        yield pages[i:end]
        if end >= len(pages):
            break
        i = end - overlap


def _classify_chunk(
    model: str,
    chunk_pages: list[PageContent],
) -> list[DocumentSegment]:
    """Send one chunk of page text to the cloud LLM and parse the response."""
    system = SYSTEM_PROMPT.format(taxonomy=taxonomy_for_prompt())

    text_lines = [
        f"Here are pages {chunk_pages[0].page_num} through "
        f"{chunk_pages[-1].page_num} of the PDF. For each page I'm showing you "
        f"the extracted text. Classify using the text content."
    ]
    for p in chunk_pages:
        text_excerpt = p.text[:2000]
        text_lines.append(
            f"\n--- PAGE {p.page_num} ({p.extraction_method}, "
            f"{p.char_count} chars) ---\n{text_excerpt}"
        )

    text_lines.append(
        "\n\nNow classify these pages. Return ONLY JSON in this shape "
        "(no markdown, no prose):\n" + RESPONSE_SCHEMA_HINT
    )
    user_content = "\n".join(text_lines)

    last_error: Optional[Exception] = None
    for attempt in range(MAX_PARSE_RETRIES + 1):
        try:
            raw_text = llm.chat_json(system, user_content, model=model)
            return _parse_segments(raw_text)
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning("  JSON parse failed on attempt %d: %s", attempt + 1, e)
            # On retry, append a stricter reminder
            user_content += (
                "\n\nREMINDER: Your previous response could not be parsed. "
                "Return ONLY a single JSON object. No markdown fences. "
                "No prose. Begin your response with { and end with }."
            )
        except llm.LLMError as e:
            # Provider/auth/quota errors won't fix themselves on retry.
            last_error = e
            break

    raise RuntimeError(f"Chunk classification failed: {last_error}")


def _parse_segments(raw_text: str) -> list[DocumentSegment]:
    """Parse the model's JSON output, tolerating common formatting quirks."""
    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        m = re.search(r"```(?:json)?\s*(.*?)```", raw_text, re.DOTALL)
        if m:
            raw_text = m.group(1).strip()
        else:
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text).strip()

    # Sometimes models emit a leading sentence like
    # "Here is the JSON:\n{...}". Strip to the outermost braces.
    first_brace = raw_text.find("{")
    last_brace = raw_text.rfind("}")
    if first_brace > 0 or last_brace < len(raw_text) - 1:
        if first_brace >= 0 and last_brace > first_brace:
            raw_text = raw_text[first_brace : last_brace + 1]

    parsed = json.loads(raw_text)

    valid_codes = set(all_codes())
    segments: list[DocumentSegment] = []
    for seg_data in parsed.get("segments", []):
        code = seg_data.get("doc_type_code", "OTHER")
        if code not in valid_codes:
            logger.warning("Unknown doc_type_code from model: %s -> OTHER", code)
            code = "OTHER"
        fields_data = seg_data.get("fields", {}) or {}

        # Coerce numeric fields the model might return as strings
        purchase_price = _coerce_number(fields_data.get("purchase_price"))
        earnest_money = _coerce_number(fields_data.get("earnest_money"))

        segments.append(DocumentSegment(
            start_page=int(seg_data["start_page"]),
            end_page=int(seg_data["end_page"]),
            doc_type_code=code,
            confidence=float(seg_data.get("confidence", 0.5)),
            rationale=seg_data.get("rationale", ""),
            fields=ExtractedFields(
                property_address=fields_data.get("property_address"),
                buyer_names=fields_data.get("buyer_names") or [],
                seller_names=fields_data.get("seller_names") or [],
                purchase_price=purchase_price,
                earnest_money=earnest_money,
                contract_date=fields_data.get("contract_date"),
                close_of_escrow_date=fields_data.get("close_of_escrow_date"),
                escrow_number=fields_data.get("escrow_number"),
                mls_number=fields_data.get("mls_number"),
                listing_agent=fields_data.get("listing_agent"),
                buyers_agent=fields_data.get("buyers_agent"),
            ),
        ))
    return segments


def _coerce_number(v) -> float | None:
    """Turn '$1,485,000' or '1485000.0' or None into a float or None."""
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


def _merge_overlapping_segments(
    segments: list[DocumentSegment],
) -> list[DocumentSegment]:
    """
    Combine segments from overlapping chunks.

    Two segments merge if they have the same doc_type_code AND their
    page ranges touch or overlap. The 1-page overlap in our chunking
    creates exactly this case at chunk boundaries.
    """
    if not segments:
        return []

    sorted_segs = sorted(segments, key=lambda s: (s.start_page, s.end_page))
    merged: list[DocumentSegment] = [sorted_segs[0]]

    for seg in sorted_segs[1:]:
        last = merged[-1]
        same_type = seg.doc_type_code == last.doc_type_code
        touching = seg.start_page <= last.end_page + 1
        if same_type and touching:
            last.end_page = max(last.end_page, seg.end_page)
            last.confidence = max(last.confidence, seg.confidence)
            last.fields = last.fields.merge(seg.fields)
        else:
            merged.append(seg)

    return merged
