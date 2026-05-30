"""
Render extracted transaction data into templates.

This module is designed as a pluggable abstraction. The same
TransactionPacket flows into any backend — Google Docs, Canva, DocuPilot,
or a local reportlab fallback. Pick whichever has the right
price/quality/setup tradeoff for your stage.

For your launch I'd start with the local PDF renderer (works offline,
no API keys, pretty enough for a coordinator one-pager) and add Canva
once you have paying customers who want marketing flyers specifically.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import TransactionPacket
from .taxonomy import get as get_doc_type

logger = logging.getLogger(__name__)


@dataclass
class TemplateContext:
    """
    The flat dictionary-like context we pass to any template engine.

    Computed once from a TransactionPacket so every renderer sees the
    same fields with the same names.
    """
    property_address: str
    buyer_names_str: str          # "John Smith and Jane Smith"
    seller_names_str: str
    purchase_price_str: str       # "$1,250,000"
    purchase_price_num: float | None
    earnest_money_str: str
    contract_date: str            # formatted "May 2, 2026"
    close_date: str
    escrow_number: str
    mls_number: str
    listing_agent: str
    buyers_agent: str
    document_count: int
    document_list: list[str]      # human-readable list of doc types found
    needs_review_count: int
    generated_at: str

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def build_context(packet: TransactionPacket) -> TemplateContext:
    """Convert a TransactionPacket into a flat template context."""
    tx = packet.transaction_fields

    def fmt_money(v: float | None) -> str:
        return f"${v:,.0f}" if v else "—"

    def fmt_date(s: str | None) -> str:
        if not s:
            return "—"
        try:
            return datetime.strptime(s, "%Y-%m-%d").strftime("%B %d, %Y")
        except ValueError:
            return s

    def join_names(names: list[str]) -> str:
        if not names:
            return "—"
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]} and {names[1]}"
        return ", ".join(names[:-1]) + f", and {names[-1]}"

    doc_list = []
    for seg in packet.segments:
        dt = get_doc_type(seg.doc_type_code)
        label = dt.label if dt else seg.doc_type_code
        doc_list.append(f"{label} (pages {seg.start_page}-{seg.end_page})")

    return TemplateContext(
        property_address=tx.property_address or "—",
        buyer_names_str=join_names(tx.buyer_names),
        seller_names_str=join_names(tx.seller_names),
        purchase_price_str=fmt_money(tx.purchase_price),
        purchase_price_num=tx.purchase_price,
        earnest_money_str=fmt_money(tx.earnest_money),
        contract_date=fmt_date(tx.contract_date),
        close_date=fmt_date(tx.close_of_escrow_date),
        escrow_number=tx.escrow_number or "—",
        mls_number=tx.mls_number or "—",
        listing_agent=tx.listing_agent or "—",
        buyers_agent=tx.buyers_agent or "—",
        document_count=len(packet.segments),
        document_list=doc_list,
        needs_review_count=len(packet.low_confidence_segments()),
        generated_at=datetime.now().strftime("%B %d, %Y at %I:%M %p"),
    )


# ---------- Renderer interface ----------

class TemplateRenderer(ABC):
    """Base class for any template backend."""

    @abstractmethod
    def render(self, context: TemplateContext, output_path: Path) -> Path:
        """Render the context to a file at output_path. Returns the path."""
        ...


# ---------- Local reportlab renderer (always works, no API needed) ----------

class LocalSummaryRenderer(TemplateRenderer):
    """
    Renders a clean one-page transaction summary as a PDF using reportlab.

    No external dependencies, no API keys. Good enough for an internal
    TC checklist or a "transaction snapshot" handout.
    """

    def render(self, context: TemplateContext, output_path: Path) -> Path:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        )

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "Title", parent=styles["Title"],
            fontSize=20, textColor=colors.HexColor("#1a1a1a"),
            spaceAfter=6,
        )
        subtitle_style = ParagraphStyle(
            "Subtitle", parent=styles["Normal"],
            fontSize=10, textColor=colors.HexColor("#666666"),
            spaceAfter=18,
        )
        h2_style = ParagraphStyle(
            "H2", parent=styles["Heading2"],
            fontSize=12, textColor=colors.HexColor("#1a1a1a"),
            spaceBefore=12, spaceAfter=6,
        )

        story = []
        story.append(Paragraph("Transaction Summary", title_style))
        story.append(Paragraph(
            f"{context.property_address} &nbsp;&middot;&nbsp; Generated {context.generated_at}",
            subtitle_style,
        ))

        # Parties + financials table
        story.append(Paragraph("Parties &amp; Financials", h2_style))
        data = [
            ["Buyer(s)", context.buyer_names_str],
            ["Seller(s)", context.seller_names_str],
            ["Purchase Price", context.purchase_price_str],
            ["Earnest Money", context.earnest_money_str],
            ["Contract Date", context.contract_date],
            ["Close of Escrow", context.close_date],
            ["Escrow #", context.escrow_number],
            ["MLS #", context.mls_number],
            ["Listing Agent", context.listing_agent],
            ["Buyer's Agent", context.buyers_agent],
        ]
        table = Table(data, colWidths=[1.6 * inch, 4.5 * inch])
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#444444")),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1),
                [colors.white, colors.HexColor("#f7f7f7")]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#e0e0e0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(table)

        # Documents found
        story.append(Paragraph(
            f"Documents in Packet ({context.document_count})", h2_style))
        for doc_line in context.document_list:
            story.append(Paragraph(f"&bull; {doc_line}", styles["Normal"]))

        if context.needs_review_count:
            story.append(Spacer(1, 12))
            warn_style = ParagraphStyle(
                "Warn", parent=styles["Normal"],
                textColor=colors.HexColor("#b54708"),
                fontSize=10,
            )
            story.append(Paragraph(
                f"&#9888; {context.needs_review_count} document(s) flagged for review. "
                f"See _NEEDS_REVIEW.txt in the transaction folder.",
                warn_style,
            ))

        doc.build(story)
        return output_path


# ---------- Canva Autofill renderer (stub, requires Enterprise API) ----------

class CanvaAutofillRenderer(TemplateRenderer):
    """
    Render via Canva's Autofill API.

    Requires:
      - Canva Connect API access (Enterprise plan)
      - A pre-built Canva template with named data fields matching the
        TemplateContext field names
      - A template_id for the design to autofill from

    Docs: https://www.canva.dev/docs/connect/api-reference/autofills/

    NOTE: I'm leaving this as a stub because (a) you don't have an
    Enterprise account yet, and (b) the API changes occasionally.
    When you're ready to add this, fill in the API call below.
    """

    def __init__(
        self,
        api_token: str,
        brand_template_id: str,
        export_format: str = "pdf",
    ):
        self.api_token = api_token
        self.brand_template_id = brand_template_id
        self.export_format = export_format

    def render(self, context: TemplateContext, output_path: Path) -> Path:
        # TODO: when you have Connect API access, uncomment and finish this.
        #
        # import requests
        #
        # # Step 1: kick off an autofill job
        # r = requests.post(
        #     "https://api.canva.com/rest/v1/autofills",
        #     headers={"Authorization": f"Bearer {self.api_token}"},
        #     json={
        #         "brand_template_id": self.brand_template_id,
        #         "data": {
        #             k: {"type": "text", "text": str(v)}
        #             for k, v in context.as_dict().items()
        #             if not isinstance(v, list)
        #         },
        #     },
        # )
        # job_id = r.json()["job"]["id"]
        #
        # # Step 2: poll until done
        # # Step 3: kick off an export job to get a PDF/PNG
        # # Step 4: download the export to output_path
        #
        # return output_path
        raise NotImplementedError(
            "Canva renderer is a stub. Use LocalSummaryRenderer until you "
            "have Canva Connect API access (Enterprise plan)."
        )


# ---------- Convenience entry point ----------

def render_summary(
    packet: TransactionPacket,
    output_path: Path,
    renderer: Optional[TemplateRenderer] = None,
) -> Path:
    """One-call helper: build context and render with the chosen backend."""
    context = build_context(packet)
    backend = renderer or LocalSummaryRenderer()
    return backend.render(context, output_path)
