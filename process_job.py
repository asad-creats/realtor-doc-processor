#!/usr/bin/env python3
"""
Command-line interface for processing one or more transaction packets.

This is what you run on your laptop when an email-job notification comes
in. Single command, sensible defaults, friendly output.

Prereqs (one-time):
  1. Set an AI provider key, e.g. GROQ_API_KEY (free at console.groq.com),
     in your environment or in a .env file next to this script.
  2. That's it — classification runs on the provider's cloud API.

Examples:
    # Basic: process one packet, output to ./jobs/
    process_job ~/Downloads/packet.pdf

    # Specify a job id (matches the one in your web app's database)
    process_job ~/Downloads/packet.pdf --job-id abc123

    # Use a custom naming pattern
    process_job ~/Downloads/packet.pdf --naming "{address}_{code}_{date}"

    # Use a different cloud model
    process_job packet.pdf --model gemma4:e4b-cloud

    # Use a fully local model (no cloud)
    process_job packet.pdf --model qwen2.5vl:7b

    # Process every PDF in a folder (e.g., when you sync from S3)
    process_job ~/jobs/incoming/*.pdf --output ~/jobs/done

    # Skip OCR (faster, only works on text-based PDFs)
    process_job ~/Downloads/packet.pdf --no-ocr
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from realtor_doc_processor import process


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Process real estate transaction packet PDFs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "pdfs",
        nargs="+",
        type=Path,
        help="One or more PDF files to process",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("./jobs"),
        help="Output directory (default: ./jobs)",
    )
    parser.add_argument(
        "--job-id",
        help="Job id to use (only valid when processing a single PDF)",
    )
    parser.add_argument(
        "--naming",
        default="{order:02d}_{code}_{date}",
        help="Filename pattern. See README for fields. "
             "Default: {order:02d}_{code}_{date}",
    )
    parser.add_argument(
        "--no-zip",
        action="store_true",
        help="Don't create a zip of the output folder",
    )
    parser.add_argument(
        "--model",
        help="Override the LLM model id. Defaults to AI_MODEL env var "
             "or the provider default (e.g. llama-3.3-70b-versatile).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging (show every stage)",
    )
    args = parser.parse_args()

    try:
        from quickstart import load_dotenv
        load_dotenv()
    except Exception:
        pass

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.job_id and len(args.pdfs) > 1:
        print("ERROR: --job-id can only be used with a single PDF.", file=sys.stderr)
        return 1

    failures = 0
    for pdf in args.pdfs:
        if not pdf.exists():
            print(f"  SKIP: {pdf} not found", file=sys.stderr)
            failures += 1
            continue
        try:
            result = process(
                pdf_path=pdf,
                output_dir=args.output,
                job_id=args.job_id,
                model=args.model,
                create_zip=not args.no_zip,
                naming_pattern=args.naming,
            )
            _print_result(result)
        except Exception as e:
            logging.exception("Failed to process %s", pdf)
            failures += 1

    return 0 if failures == 0 else 2


def _print_result(result) -> None:
    """Friendly summary after a successful job."""
    p = result.packet
    tx = p.transaction_fields
    print()
    print("=" * 64)
    print(f"  JOB {result.job_id} COMPLETE")
    print("=" * 64)
    print(f"  Property:        {tx.property_address or '(not detected)'}")
    print(f"  Buyers:          {', '.join(tx.buyer_names) or '(not detected)'}")
    print(f"  Sellers:         {', '.join(tx.seller_names) or '(not detected)'}")
    if tx.purchase_price:
        print(f"  Purchase price:  ${tx.purchase_price:,.0f}")
    print(f"  Documents found: {len(p.segments)}")
    review = p.low_confidence_segments()
    if review:
        print(f"  ! Needs review:  {len(review)} segment(s) -- see _NEEDS_REVIEW.txt")
    else:
        print("  All segments classified with high confidence")
    print()
    print(f"  Folder:  {result.transaction_folder}")
    if result.zip_path:
        print(f"  Zip:     {result.zip_path}")
    print(f"  Summary: {result.summary_pdf}")
    print()


if __name__ == "__main__":
    sys.exit(main())
