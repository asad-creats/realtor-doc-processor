"""
PDF text + thumbnail extraction.

Strategy:
1. Try fast path with pdfplumber (works on text-based PDFs — most modern ones).
2. If pages come back empty/short, fall back to OCR via pytesseract.
3. Always render a small thumbnail per page so the LLM can use vision
   for documents where text alone is ambiguous (scanned signature pages,
   stamped forms, etc.).

The output is a list of `PageContent` — one per page. Downstream code
never has to know which extraction method was used.
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
from pdf2image import convert_from_path
from PIL import Image

logger = logging.getLogger(__name__)

# If a page has fewer than this many text characters, we treat it as scanned
# and trigger OCR. Tuned empirically — most real text pages have 500+ chars,
# scanned pages have 0-50 (just noise from headers/page numbers).
OCR_FALLBACK_THRESHOLD = 100

# Thumbnail dims for the LLM. Small enough to keep token costs down,
# large enough that document headers/logos are readable.
THUMBNAIL_DPI = 80
THUMBNAIL_MAX_WIDTH = 800


@dataclass
class PageContent:
    page_num: int               # 1-indexed
    text: str
    thumbnail_b64: str          # base64-encoded PNG, no data: prefix
    extraction_method: str      # "text" or "ocr"
    char_count: int


def extract_pdf(
    pdf_path: Path,
    ocr_enabled: bool = True,
    render_thumbnails: bool = False,
) -> list[PageContent]:
    """
    Extract text (and optionally thumbnails) from every page of a PDF.

    Args:
        pdf_path: path to the PDF file
        ocr_enabled: if False, skip OCR fallback (useful for testing)
        render_thumbnails: if True, render a per-page image (needs Poppler).
            Only needed for vision models; the default cloud path is text-only,
            so this defaults to False and Poppler isn't required for text PDFs.

    Returns:
        list of PageContent, one per page, in order
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    logger.info("Extracting %s", pdf_path.name)

    # Step 1: text extraction with pdfplumber (no Poppler needed)
    page_texts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            page_texts.append(text.strip())

    num_pages = len(page_texts)
    logger.info("  %d pages, text extraction complete", num_pages)

    # Step 2: render thumbnails only if requested (vision models). Needs Poppler.
    thumbnails = None
    if render_thumbnails:
        thumbnails = convert_from_path(str(pdf_path), dpi=THUMBNAIL_DPI)

    # Step 3: figure out which pages need OCR
    needs_ocr = [
        i for i, t in enumerate(page_texts)
        if len(t) < OCR_FALLBACK_THRESHOLD
    ]

    if needs_ocr and ocr_enabled:
        logger.info("  %d pages need OCR fallback", len(needs_ocr))
        # Render at higher DPI just for OCR pages
        ocr_images = convert_from_path(
            str(pdf_path),
            dpi=200,
            first_page=min(needs_ocr) + 1,
            last_page=max(needs_ocr) + 1,
        )
        # Map back to page indices
        offset = min(needs_ocr)
        try:
            import pytesseract
            for page_idx in needs_ocr:
                img = ocr_images[page_idx - offset]
                ocr_text = pytesseract.image_to_string(img)
                page_texts[page_idx] = ocr_text.strip()
        except ImportError:
            logger.warning("pytesseract not installed, skipping OCR")
        except pytesseract.TesseractNotFoundError:
            logger.warning(
                "Tesseract engine not found on PATH, skipping OCR. "
                "Scanned pages will have little/no text. "
                "Install it from github.com/UB-Mannheim/tesseract/wiki "
                "and add it to your PATH to enable OCR."
            )
        except Exception as e:  # don't let one bad OCR page kill the whole job
            logger.warning("OCR failed (%s), continuing without it", e)

    # Step 4: build PageContent list
    results = []
    for i in range(num_pages):
        b64 = ""
        if thumbnails is not None:
            b64 = _img_to_b64(_resize_for_thumbnail(thumbnails[i]))
        results.append(PageContent(
            page_num=i + 1,
            text=page_texts[i],
            thumbnail_b64=b64,
            extraction_method="ocr" if i in needs_ocr else "text",
            char_count=len(page_texts[i]),
        ))

    return results


def _resize_for_thumbnail(img: Image.Image) -> Image.Image:
    """Cap the width of the thumbnail so we don't blow our token budget."""
    if img.width <= THUMBNAIL_MAX_WIDTH:
        return img
    ratio = THUMBNAIL_MAX_WIDTH / img.width
    new_size = (THUMBNAIL_MAX_WIDTH, int(img.height * ratio))
    return img.resize(new_size, Image.LANCZOS)


def _img_to_b64(img: Image.Image) -> str:
    """Convert a PIL image to base64-encoded PNG."""
    # Convert to RGB if needed (some PDFs render as RGBA or P)
    if img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")
