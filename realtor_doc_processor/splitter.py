"""
Split a classified PDF into individual files with proper naming.

The naming convention is configurable per user. The default follows the
most common TC convention I've seen:

  {transaction_short}_{doc_code}_{date}.pdf

where:
  - transaction_short = property address shortened to "123MainSt"
  - doc_code = the taxonomy short code (RPA, TDS, etc.)
  - date = contract date or processing date as YYYY-MM-DD

If two segments produce the same filename (e.g., two addenda on the
same day), we suffix with _2, _3, etc.

The output structure is:

  output_dir/
    {transaction_short}/
      01_RPA_2026-05-02.pdf
      02_CounterOffer_2026-05-02.pdf
      ...
      _summary.json          <- the full TransactionPacket as JSON
      _NEEDS_REVIEW.txt      <- list of low-confidence segments (if any)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from .models import TransactionPacket, DocumentSegment
from .taxonomy import get as get_doc_type

logger = logging.getLogger(__name__)


def split_packet(
    pdf_path: Path,
    packet: TransactionPacket,
    output_dir: Path,
    naming_pattern: str = "{order:02d}_{code}_{date}",
) -> Path:
    """
    Split the source PDF according to the packet's segments.

    Args:
        pdf_path: original combined PDF
        packet: classification result from classifier.classify_packet
        output_dir: parent directory for output (a subfolder will be created)
        naming_pattern: format string. Available fields:
            - {order}: 1-indexed order in the packet
            - {code}: doc type code (RPA, TDS, etc.)
            - {label}: full doc type label (spaces removed)
            - {date}: contract_date or "undated"
            - {address}: short property address ("123MainSt") or "noaddress"

    Returns:
        Path to the created transaction folder
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)

    # Build the transaction folder name
    addr_short = _shorten_address(packet.transaction_fields.property_address)
    folder_name = addr_short or f"transaction_{packet.job_id}"
    tx_folder = output_dir / folder_name
    tx_folder.mkdir(parents=True, exist_ok=True)

    logger.info("Splitting %d segments into %s", len(packet.segments), tx_folder)

    reader = PdfReader(str(pdf_path))
    used_names: set[str] = set()

    for order, seg in enumerate(packet.segments, start=1):
        filename = _build_filename(
            seg, order, packet, naming_pattern, used_names
        )
        used_names.add(filename)

        out_path = tx_folder / f"{filename}.pdf"
        _write_segment(reader, seg, out_path)
        logger.info("  -> %s (pages %d-%d)",
                    out_path.name, seg.start_page, seg.end_page)

    # Write the JSON summary
    (tx_folder / "_summary.json").write_text(packet.to_json())

    # Write a review file if there are low-confidence segments
    review_items = packet.low_confidence_segments()
    if review_items:
        _write_review_file(tx_folder / "_NEEDS_REVIEW.txt", review_items)

    return tx_folder


def _build_filename(
    seg: DocumentSegment,
    order: int,
    packet: TransactionPacket,
    pattern: str,
    used: set[str],
) -> str:
    """Build a filename, ensuring uniqueness."""
    doc_type = get_doc_type(seg.doc_type_code)
    label = doc_type.label.replace(" ", "") if doc_type else seg.doc_type_code
    label = re.sub(r"[^A-Za-z0-9]", "", label)

    date_str = seg.fields.contract_date or packet.transaction_fields.contract_date or "undated"
    addr_short = _shorten_address(packet.transaction_fields.property_address) or "noaddress"

    base = pattern.format(
        order=order,
        code=seg.doc_type_code,
        label=label,
        date=date_str,
        address=addr_short,
    )
    base = _sanitize(base)

    if base not in used:
        return base

    # Disambiguate with a counter
    n = 2
    while f"{base}_{n}" in used:
        n += 1
    return f"{base}_{n}"


def _write_segment(reader: PdfReader, seg: DocumentSegment, out_path: Path) -> None:
    """Write the pages [start_page, end_page] (1-indexed, inclusive) to a new PDF."""
    writer = PdfWriter()
    # pypdf uses 0-indexed pages
    for page_idx in range(seg.start_page - 1, seg.end_page):
        if page_idx < 0 or page_idx >= len(reader.pages):
            logger.warning("Page %d out of range, skipping", page_idx + 1)
            continue
        writer.add_page(reader.pages[page_idx])
    with open(out_path, "wb") as f:
        writer.write(f)


def _shorten_address(address: str | None) -> str | None:
    """
    Convert "123 Main Street, San Francisco, CA 94110" -> "123MainSt".

    Keeps the street number and street name, drops city/state/zip.
    """
    if not address:
        return None
    # Take the part before the first comma
    street_part = address.split(",")[0].strip()
    # Strip everything except alphanumerics
    short = re.sub(r"[^A-Za-z0-9]", "", street_part)
    # Truncate to keep filenames reasonable
    return short[:40] if short else None


def _sanitize(name: str) -> str:
    """Make a string safe for use as a filename on Windows/Mac/Linux."""
    name = re.sub(r"[<>:\"/\\|?*]", "_", name)
    name = name.strip(". ")
    return name or "untitled"


def _write_review_file(path: Path, items: list[DocumentSegment]) -> None:
    """Write a human-readable list of segments needing review."""
    lines = [
        "DOCUMENTS THAT NEED HUMAN REVIEW",
        "=" * 60,
        "",
        "The AI flagged these segments because confidence was low or the",
        "document type was unclear. Open them and check classification",
        "before delivering to the customer.",
        "",
    ]
    for seg in items:
        doc_type = get_doc_type(seg.doc_type_code)
        label = doc_type.label if doc_type else seg.doc_type_code
        lines.extend([
            f"Pages {seg.start_page}-{seg.end_page}: {label} ({seg.doc_type_code})",
            f"  Confidence: {seg.confidence:.2f}",
            f"  AI rationale: {seg.rationale}",
            "",
        ])
    path.write_text("\n".join(lines))
