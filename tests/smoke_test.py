"""
Smoke test the full pipeline against the synthetic packet.

Mocks the Claude classifier so we can verify the plumbing — extraction,
splitting, naming, summary rendering — without needing an API key.
"""

import logging
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Make package importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from realtor_doc_processor.models import (
    DocumentSegment, ExtractedFields, TransactionPacket
)
from realtor_doc_processor.pipeline import process

logging.basicConfig(level=logging.INFO, format="%(message)s")

PACKET_PDF = Path(__file__).parent.parent / "examples" / "synthetic_packet.pdf"
OUT_DIR = Path(tempfile.gettempdir()) / "rdp_smoke_test"

# This is what we EXPECT Claude to return for our synthetic packet.
# In the real run, the classifier produces this from the PDF; here we
# just stub it so we can validate splitter + renamer + summary work.
def _fake_classify(pages, job_id, source_filename, **kwargs):
    return TransactionPacket(
        job_id=job_id,
        source_filename=source_filename,
        total_pages=len(pages),
        segments=[
            DocumentSegment(
                start_page=1, end_page=2, doc_type_code="RPA", confidence=0.97,
                rationale="Form ID 'C.A.R. Form RPA' clearly visible. Has buyer/seller, price, dates.",
                fields=ExtractedFields(
                    property_address="847 Hillcrest Avenue, Berkeley, CA 94708",
                    buyer_names=["Marcus Chen", "Priya Chen"],
                    seller_names=["Robert Hernandez", "Linda Hernandez"],
                    purchase_price=1485000.0,
                    earnest_money=45000.0,
                    contract_date="2026-04-18",
                    close_of_escrow_date="2026-05-30",
                    escrow_number="BERK-2026-08471",
                    mls_number="425067843",
                    listing_agent="Sarah Williams",
                    buyers_agent="David Park",
                ),
            ),
            DocumentSegment(
                start_page=3, end_page=4, doc_type_code="TDS", confidence=0.95,
                rationale="Header reads 'Real Estate Transfer Disclosure Statement'.",
                fields=ExtractedFields(
                    property_address="847 Hillcrest Avenue, Berkeley, CA 94708",
                    seller_names=["Robert Hernandez", "Linda Hernandez"],
                    buyer_names=["Marcus Chen", "Priya Chen"],
                ),
            ),
            DocumentSegment(
                start_page=5, end_page=5, doc_type_code="LeadPaint", confidence=0.96,
                rationale="Federal Lead Disclosure Form for pre-1978 housing.",
                fields=ExtractedFields(
                    property_address="847 Hillcrest Avenue, Berkeley, CA 94708",
                ),
            ),
            DocumentSegment(
                start_page=6, end_page=6, doc_type_code="WireInstructions", confidence=0.92,
                rationale="Bank routing/account info for earnest money deposit.",
                fields=ExtractedFields(
                    escrow_number="BERK-2026-08471",
                    earnest_money=45000.0,
                ),
            ),
        ],
        transaction_fields=ExtractedFields(
            property_address="847 Hillcrest Avenue, Berkeley, CA 94708",
            buyer_names=["Marcus Chen", "Priya Chen"],
            seller_names=["Robert Hernandez", "Linda Hernandez"],
            purchase_price=1485000.0,
            earnest_money=45000.0,
            contract_date="2026-04-18",
            close_of_escrow_date="2026-05-30",
            escrow_number="BERK-2026-08471",
            mls_number="425067843",
            listing_agent="Sarah Williams",
            buyers_agent="David Park",
        ),
    )


with patch("realtor_doc_processor.pipeline.classify_packet", side_effect=_fake_classify):
    result = process(
        pdf_path=PACKET_PDF,
        output_dir=OUT_DIR,
        job_id="smoke_test_001",
    )

print()
print("=" * 60)
print("RESULT")
print("=" * 60)
print(f"Transaction folder: {result.transaction_folder}")
print(f"Files produced:")
for f in sorted(result.transaction_folder.iterdir()):
    print(f"  {f.name}  ({f.stat().st_size:,} bytes)")
print()
print(f"Zip: {result.zip_path}")
print(f"Summary PDF: {result.summary_pdf}")
