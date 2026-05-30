"""
Realtor Document Processor.

A pipeline that takes a real-estate transaction packet PDF (or folder
of mixed PDFs), classifies and splits each document, extracts key
transaction fields, and produces a renamed folder + summary PDF.

Usage:
    from realtor_doc_processor import process

    result = process(
        pdf_path="packet.pdf",
        output_dir="./out",
    )
    print(f"Done. Files in {result.transaction_folder}")
"""

from .models import (
    DocumentSegment,
    ExtractedFields,
    TransactionPacket,
)
from .pipeline import PipelineResult, process
from .template_render import (
    CanvaAutofillRenderer,
    LocalSummaryRenderer,
    TemplateContext,
    TemplateRenderer,
    build_context,
    render_summary,
)

__version__ = "0.2.0"

__all__ = [
    "process",
    "PipelineResult",
    "TransactionPacket",
    "DocumentSegment",
    "ExtractedFields",
    "TemplateContext",
    "TemplateRenderer",
    "LocalSummaryRenderer",
    "CanvaAutofillRenderer",
    "build_context",
    "render_summary",
]
