"""
Build a synthetic combined transaction packet for testing.

Creates a single PDF that contains 4 fake real-estate documents glued
together — exactly the shape of a real TC's nightmare upload.
"""

from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak

OUT = Path(__file__).parent / "synthetic_packet.pdf"

styles = getSampleStyleSheet()
title = ParagraphStyle("T", parent=styles["Title"], fontSize=14, spaceAfter=12)
form_id = ParagraphStyle("F", parent=styles["Normal"], fontSize=8, textColor="#888888")
body = styles["Normal"]


def doc_rpa():
    return [
        Paragraph("CALIFORNIA RESIDENTIAL PURCHASE AGREEMENT AND JOINT ESCROW INSTRUCTIONS", title),
        Paragraph("C.A.R. Form RPA, Revised 12/24", form_id),
        Spacer(1, 12),
        Paragraph("1. PROPERTY TO BE ACQUIRED. The real property to be acquired is "
                  "<b>847 Hillcrest Avenue, Berkeley, CA 94708</b>, situated in Alameda County, "
                  "described as: Lot 14, Block 3, Hillcrest Heights subdivision.", body),
        Spacer(1, 8),
        Paragraph("2. PARTIES. <b>Buyer: Marcus Chen and Priya Chen</b> "
                  "agree to purchase the Property from <b>Seller: Robert Hernandez and Linda Hernandez</b>.", body),
        Spacer(1, 8),
        Paragraph("3. AGENCY. Listing Agent: Sarah Williams (DRE# 01234567), Coldwell Banker. "
                  "Buyer's Agent: David Park (DRE# 02345678), Compass.", body),
        Spacer(1, 8),
        Paragraph("4. PURCHASE PRICE. The Purchase Price offered is "
                  "<b>$1,485,000</b> (One Million Four Hundred Eighty-Five Thousand Dollars).", body),
        Spacer(1, 8),
        Paragraph("5. EARNEST MONEY DEPOSIT. Buyer shall deposit <b>$45,000</b> within "
                  "3 business days of acceptance with First American Title.", body),
        Spacer(1, 8),
        Paragraph("6. CONTRACT DATE: <b>April 18, 2026</b>. Close of Escrow shall occur on or before "
                  "<b>May 30, 2026</b>.", body),
        Spacer(1, 8),
        Paragraph("MLS #: 425067843", body),
        PageBreak(),
        Paragraph("PURCHASE AGREEMENT — Page 2", title),
        Paragraph("7. CONTINGENCIES. Buyer's obligations are contingent on (a) inspection, "
                  "(b) loan approval, and (c) appraisal. Standard 17-day removal period applies.", body),
        Spacer(1, 8),
        Paragraph("8. ESCROW. Escrow #: BERK-2026-08471. Escrow Officer: Janet Lopez, "
                  "First American Title, Berkeley branch.", body),
        Spacer(1, 8),
        Paragraph("Signed: Marcus Chen ___________ Date: 4/18/2026", body),
        Paragraph("Signed: Priya Chen ___________ Date: 4/18/2026", body),
        Paragraph("Accepted: Robert Hernandez ___________ Date: 4/19/2026", body),
        Paragraph("Accepted: Linda Hernandez ___________ Date: 4/19/2026", body),
    ]


def doc_tds():
    return [
        Paragraph("REAL ESTATE TRANSFER DISCLOSURE STATEMENT", title),
        Paragraph("C.A.R. Form TDS, Revised 6/24", form_id),
        Spacer(1, 12),
        Paragraph("This disclosure concerns the real property at "
                  "<b>847 Hillcrest Avenue, Berkeley, CA 94708</b>.", body),
        Spacer(1, 8),
        Paragraph("Seller(s): Robert Hernandez, Linda Hernandez. This statement is a disclosure "
                  "of the condition of the above property in compliance with Section 1102 of the "
                  "California Civil Code as of the date signed below.", body),
        Spacer(1, 8),
        Paragraph("THE SELLER DISCLOSES THE FOLLOWING INFORMATION: "
                  "The subject property has the following items checked: range, oven, dishwasher, "
                  "trash compactor, garbage disposal, washer/dryer hookups, central heating, "
                  "central air conditioning, smoke detector(s), carbon monoxide detector(s).", body),
        Spacer(1, 8),
        Paragraph("Are you (Seller) aware of any significant defects in any of the following? "
                  "Roof: NO. Walls: NO. Insulation: NO. Floors: Minor wear in upstairs hallway. "
                  "Plumbing/Sewers: Replaced main line 2019.", body),
        PageBreak(),
        Paragraph("TDS — Page 2", title),
        Paragraph("Seller signature: Robert Hernandez ___________ Date: 4/19/2026", body),
        Paragraph("Seller signature: Linda Hernandez ___________ Date: 4/19/2026", body),
        Paragraph("Buyer acknowledgment: Marcus Chen ___________ Date: 4/22/2026", body),
        Paragraph("Buyer acknowledgment: Priya Chen ___________ Date: 4/22/2026", body),
    ]


def doc_lead_paint():
    return [
        Paragraph("DISCLOSURE OF INFORMATION ON LEAD-BASED PAINT AND/OR LEAD-BASED PAINT HAZARDS", title),
        Paragraph("Federal Lead Disclosure Form (FLD), required for housing built before 1978", form_id),
        Spacer(1, 12),
        Paragraph("Property: <b>847 Hillcrest Avenue, Berkeley, CA 94708</b>", body),
        Spacer(1, 8),
        Paragraph("LEAD WARNING STATEMENT. Every purchaser of any interest in residential real "
                  "property on which a residential dwelling was built prior to 1978 is notified that "
                  "such property may present exposure to lead from lead-based paint that may place "
                  "young children at risk of developing lead poisoning.", body),
        Spacer(1, 8),
        Paragraph("Seller's Disclosure: Seller has no knowledge of lead-based paint or lead-based "
                  "paint hazards in the housing. Records: Seller has no reports or records pertaining "
                  "to lead-based paint or lead-based paint hazards in the housing.", body),
        Spacer(1, 8),
        Paragraph("Purchaser's Acknowledgment: Purchaser has received the pamphlet \"Protect Your "
                  "Family From Lead in Your Home.\" Purchaser has waived the opportunity to conduct "
                  "a risk assessment.", body),
        Spacer(1, 8),
        Paragraph("Signed by Robert Hernandez (Seller) on April 19, 2026.", body),
        Paragraph("Signed by Marcus Chen (Buyer) on April 22, 2026.", body),
    ]


def doc_wire_instructions():
    return [
        Paragraph("WIRE TRANSFER INSTRUCTIONS", title),
        Paragraph("First American Title Insurance Company — Berkeley Branch", form_id),
        Spacer(1, 12),
        Paragraph("Date: April 22, 2026", body),
        Paragraph("RE: Escrow #BERK-2026-08471", body),
        Paragraph("Property: 847 Hillcrest Avenue, Berkeley, CA 94708", body),
        Spacer(1, 12),
        Paragraph("Please wire your earnest money deposit of <b>$45,000.00</b> to the following account:", body),
        Spacer(1, 12),
        Paragraph("Bank: Wells Fargo Bank N.A.", body),
        Paragraph("Bank Address: 420 Montgomery Street, San Francisco, CA 94104", body),
        Paragraph("ABA / Routing #: 121000248", body),
        Paragraph("Account Name: First American Title Insurance Co. Trust Account", body),
        Paragraph("Account #: 4159823071", body),
        Paragraph("Reference: BERK-2026-08471 / Chen Purchase", body),
        Spacer(1, 12),
        Paragraph("FRAUD WARNING: Verify these wire instructions by phone before sending. "
                  "Call our office at (510) 555-0182. Do not rely on emailed instructions alone.", body),
    ]


story = []
story.extend(doc_rpa())
story.append(PageBreak())
story.extend(doc_tds())
story.append(PageBreak())
story.extend(doc_lead_paint())
story.append(PageBreak())
story.extend(doc_wire_instructions())

doc = SimpleDocTemplate(
    str(OUT), pagesize=letter,
    leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    topMargin=0.75 * inch, bottomMargin=0.75 * inch,
)
doc.build(story)
print(f"Created {OUT}")
