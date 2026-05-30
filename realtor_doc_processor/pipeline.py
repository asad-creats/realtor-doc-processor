"""
End-to-end pipeline: PDF in, organized folder out.

This is what your local processing tool calls. The web app's "submit job"
endpoint calls the SAME function — that's the whole point of the
manual-then-automated migration plan.
"""

from __future__ import annotations

import logging
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import llm
from .classifier import classify_packet, is_vision_model
from .models import TransactionPacket
from .pdf_extract import extract_pdf
from .splitter import split_packet
from .template_render import LocalSummaryRenderer, render_summary

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    job_id: str
    packet: TransactionPacket
    transaction_folder: Path
    summary_pdf: Path
    zip_path: Optional[Path]


def process(
    pdf_path: Path,
    output_dir: Path,
    job_id: Optional[str] = None,
    model: Optional[str] = None,
    host: Optional[str] = None,
    create_zip: bool = True,
    naming_pattern: str = "{order:02d}_{code}_{date}",
) -> PipelineResult:
    """
    Run the full pipeline.

    Args:
        pdf_path: input PDF (combined packet, or a single document)
        output_dir: where the transaction folder will be created
        job_id: optional job id; auto-generated if not provided
        model: override the LLM model id. Defaults to env AI_MODEL.
        host:  ignored (legacy arg, kept for backwards compatibility).
        create_zip: also create a zip of the transaction folder
        naming_pattern: see splitter.split_packet

    Returns:
        PipelineResult with paths to all produced artifacts.
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    job_id = job_id or uuid.uuid4().hex[:12]

    logger.info("=" * 60)
    logger.info("Job %s: processing %s", job_id, pdf_path.name)
    logger.info("=" * 60)

    # 1. Extract pages. Only render page images for vision models; the default
    #    cloud model is text-only, so we skip thumbnails (and Poppler) entirely.
    resolved_model = llm.active_model(model)
    pages = extract_pdf(pdf_path, render_thumbnails=is_vision_model(resolved_model))
    logger.info("Stage 1 done: %d pages extracted", len(pages))

    # 2. Classify with the cloud LLM
    packet = classify_packet(
        pages=pages,
        job_id=job_id,
        source_filename=pdf_path.name,
        model=model,
        host=host,
    )
    logger.info("Stage 2 done: %d documents identified", len(packet.segments))

    # 3. Split + rename
    tx_folder = split_packet(
        pdf_path=pdf_path,
        packet=packet,
        output_dir=output_dir,
        naming_pattern=naming_pattern,
    )
    logger.info("Stage 3 done: split into %s", tx_folder)

    # 4. Render summary PDF
    summary_pdf = tx_folder / "_TransactionSummary.pdf"
    render_summary(packet, summary_pdf, renderer=LocalSummaryRenderer())
    logger.info("Stage 4 done: summary at %s", summary_pdf)

    # 5. Optional zip
    zip_path = None
    if create_zip:
        zip_path = output_dir / f"{tx_folder.name}.zip"
        _zip_folder(tx_folder, zip_path)
        logger.info("Stage 5 done: zipped to %s", zip_path)

    return PipelineResult(
        job_id=job_id,
        packet=packet,
        transaction_folder=tx_folder,
        summary_pdf=summary_pdf,
        zip_path=zip_path,
    )


def _zip_folder(folder: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in folder.rglob("*"):
            if file.is_file():
                zf.write(file, arcname=file.relative_to(folder.parent))
