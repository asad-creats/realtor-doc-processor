"""
Real estate document taxonomy.

This is the master list of document types we recognize. It's deliberately
flat (no hierarchy) and uses short codes so they fit in filenames.

The taxonomy is the single most important piece of this system. The AI's
accuracy is bounded by the quality of this list. When you find a doc type
that gets misclassified or gets dumped into "OTHER", add it here.

Currently focused on California (CAR) forms since that's the most
standardized market. Add state-specific variants as you expand.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DocType:
    code: str           # short code for filenames, e.g. "RPA"
    label: str          # human-readable name
    aliases: tuple      # alternate names the AI might encounter
    description: str    # hint for the classifier prompt
    typical_pages: int  # rough length, helps boundary detection


# Core CA residential transaction documents
DOC_TYPES = [
    DocType(
        code="RPA",
        label="Residential Purchase Agreement",
        aliases=("Purchase Agreement", "CAR RPA", "RPA-CA", "Purchase Contract"),
        description="The main contract. Has buyer/seller names, property address, purchase price, "
                    "earnest money, close of escrow date. Usually 10-16 pages, signed.",
        typical_pages=14,
    ),
    DocType(
        code="CounterOffer",
        label="Counter Offer",
        aliases=("Seller Counter Offer", "Buyer Counter Offer", "SCO", "BCO"),
        description="A counter to the original offer. References the RPA and changes specific terms.",
        typical_pages=2,
    ),
    DocType(
        code="Addendum",
        label="Addendum",
        aliases=("ADM", "Contract Addendum", "Addendum to Purchase Agreement"),
        description="Generic addendum modifying the purchase agreement. Often numbered.",
        typical_pages=2,
    ),
    DocType(
        code="TDS",
        label="Transfer Disclosure Statement",
        aliases=("Real Estate Transfer Disclosure", "Seller Disclosure"),
        description="Seller's disclosure of property condition. Required by CA law.",
        typical_pages=3,
    ),
    DocType(
        code="SPQ",
        label="Seller Property Questionnaire",
        aliases=("Seller Questionnaire",),
        description="Detailed seller questionnaire about property history and condition.",
        typical_pages=4,
    ),
    DocType(
        code="AVID",
        label="Agent Visual Inspection Disclosure",
        aliases=("Agent Inspection",),
        description="Agent's visual inspection notes of the property.",
        typical_pages=2,
    ),
    DocType(
        code="LeadPaint",
        label="Lead-Based Paint Disclosure",
        aliases=("FLD", "Lead Paint", "Federal Lead-Based Paint Disclosure"),
        description="Federal lead paint disclosure for homes built before 1978.",
        typical_pages=2,
    ),
    DocType(
        code="NHD",
        label="Natural Hazard Disclosure",
        aliases=("Natural Hazard Report", "NHD Report", "Hazard Disclosure"),
        description="Discloses if property is in flood/fire/earthquake zones. Often a 3rd party report.",
        typical_pages=10,
    ),
    DocType(
        code="WireInstructions",
        label="Wire Instructions",
        aliases=("Wiring Instructions", "Wire Transfer Instructions"),
        description="Bank wire instructions for earnest money or closing funds. CRITICAL — contains "
                    "routing/account numbers. Often a single page from escrow or title.",
        typical_pages=1,
    ),
    DocType(
        code="PrelimTitle",
        label="Preliminary Title Report",
        aliases=("Prelim", "Title Report", "Preliminary Report"),
        description="Title company's preliminary report on liens, easements, vesting.",
        typical_pages=15,
    ),
    DocType(
        code="EscrowInstructions",
        label="Escrow Instructions",
        aliases=("General Provisions", "Escrow General Provisions"),
        description="Escrow company's instructions and general provisions.",
        typical_pages=8,
    ),
    DocType(
        code="CommissionAgreement",
        label="Commission Agreement",
        aliases=("Compensation Agreement", "Broker Compensation"),
        description="Agreement on commission split / broker compensation.",
        typical_pages=2,
    ),
    DocType(
        code="ListingAgreement",
        label="Listing Agreement",
        aliases=("Residential Listing Agreement", "RLA"),
        description="Contract between seller and listing broker.",
        typical_pages=8,
    ),
    DocType(
        code="BuyerRepAgreement",
        label="Buyer Representation Agreement",
        aliases=("BRBC", "Buyer Broker Agreement"),
        description="Contract between buyer and buyer's agent.",
        typical_pages=4,
    ),
    DocType(
        code="HOA",
        label="HOA Documents",
        aliases=("CC&Rs", "HOA Disclosure", "HOA Bylaws", "HOA Financials"),
        description="Homeowner association documents — bylaws, CC&Rs, financials, meeting minutes.",
        typical_pages=50,
    ),
    DocType(
        code="InspectionReport",
        label="Inspection Report",
        aliases=("Home Inspection", "Property Inspection Report"),
        description="Home inspector's report. Usually has photos and item-by-item findings.",
        typical_pages=30,
    ),
    DocType(
        code="TermiteReport",
        label="Termite / Pest Report",
        aliases=("WDO Report", "Wood Destroying Organism Report", "Pest Inspection"),
        description="Termite/pest inspection report. Section 1 and Section 2 findings.",
        typical_pages=8,
    ),
    DocType(
        code="Appraisal",
        label="Appraisal Report",
        aliases=("Property Appraisal", "Appraised Value Report"),
        description="Lender's appraisal of property value.",
        typical_pages=25,
    ),
    DocType(
        code="LoanEstimate",
        label="Loan Estimate",
        aliases=("LE", "TRID Loan Estimate"),
        description="Lender's loan estimate disclosure (TRID required).",
        typical_pages=3,
    ),
    DocType(
        code="ClosingDisclosure",
        label="Closing Disclosure",
        aliases=("CD", "TRID Closing Disclosure", "Final CD"),
        description="Final closing disclosure with all costs (TRID required).",
        typical_pages=5,
    ),
    DocType(
        code="ProofOfFunds",
        label="Proof of Funds",
        aliases=("POF", "Bank Statement"),
        description="Buyer's bank statement or letter showing they have funds.",
        typical_pages=2,
    ),
    DocType(
        code="PreApproval",
        label="Pre-Approval Letter",
        aliases=("Pre-Approval", "Loan Pre-Approval", "Mortgage Pre-Qual"),
        description="Lender's letter saying buyer is pre-approved for a loan amount.",
        typical_pages=1,
    ),
    DocType(
        code="ContingencyRemoval",
        label="Contingency Removal",
        aliases=("CR", "Removal of Contingencies"),
        description="Form removing inspection / loan / appraisal contingencies.",
        typical_pages=1,
    ),
    DocType(
        code="GrantDeed",
        label="Grant Deed",
        aliases=("Deed", "Quitclaim Deed", "Warranty Deed"),
        description="The deed transferring ownership.",
        typical_pages=2,
    ),
    DocType(
        code="OTHER",
        label="Unknown / Other",
        aliases=(),
        description="Use ONLY if the document genuinely doesn't fit any category above.",
        typical_pages=0,
    ),
]


# Build lookup maps
_BY_CODE = {dt.code: dt for dt in DOC_TYPES}


def get(code: str) -> Optional[DocType]:
    """Return the DocType for a given code, or None if not found."""
    return _BY_CODE.get(code)


def all_codes() -> list[str]:
    """Return all valid doc type codes."""
    return [dt.code for dt in DOC_TYPES]


def taxonomy_for_prompt() -> str:
    """Render the taxonomy as a string suitable for inclusion in the LLM prompt."""
    lines = []
    for dt in DOC_TYPES:
        line = f"- {dt.code} ({dt.label}): {dt.description}"
        if dt.aliases:
            line += f" Also called: {', '.join(dt.aliases)}."
        lines.append(line)
    return "\n".join(lines)
