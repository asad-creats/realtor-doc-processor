#!/usr/bin/env python3
"""
One-command quickstart / doctor for the Realtor Document Processor.

Run this first. It loads your .env, verifies the cloud AI provider is
configured, builds the demo packet if needed, and runs the real pipeline
end-to-end so you can see live output.

Usage:
    python quickstart.py                 # check, then run the demo packet
    python quickstart.py --check         # only run the environment checks
    python quickstart.py my_packet.pdf   # run against your own PDF

Exit codes: 0 = success, 1 = a hard prerequisite is missing.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
DEMO_PDF = ROOT / "examples" / "synthetic_packet.pdf"
OUTPUT_DIR = ROOT / "jobs"

OK = "[ OK ]"
WARN = "[WARN]"
FAIL = "[FAIL]"


def _print(tag: str, msg: str) -> None:
    print(f"  {tag}  {msg}")


def load_dotenv() -> None:
    """Minimal .env loader (no dependency). Sets vars that aren't already set."""
    import os
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def check_python_deps() -> bool:
    """Verify the core importable packages the pipeline needs."""
    required = {"httpx": "httpx", "pypdf": "pypdf",
                "pdfplumber": "pdfplumber", "reportlab": "reportlab"}
    missing = [pkg for mod, pkg in required.items()
               if not _can_import(mod)]
    if missing:
        _print(FAIL, f"Missing Python packages: {', '.join(missing)}")
        _print("", f"Fix:  pip install {' '.join(missing)}")
        return False
    _print(OK, "Core Python dependencies installed")
    return True


def _can_import(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


def check_ai_provider() -> tuple[bool, str | None]:
    """Verify a cloud AI provider key is configured."""
    from realtor_doc_processor import llm
    provider = llm.provider_name()
    if llm.is_configured():
        _print(OK, f"AI provider ready: {provider} (model: {llm.active_model()})")
        return True, llm.active_model()
    _print(FAIL, f"AI provider '{provider}' has no API key.")
    _print("", f"Set {provider.upper()}_API_KEY in your environment or in a .env file.")
    _print("", "Get a free Groq key at https://console.groq.com/keys")
    return False, None


def check_optional_ocr() -> None:
    """OCR/vision extras are optional — only needed for scanned PDFs."""
    have_poppler = bool(shutil.which("pdftoppm"))
    have_tesseract = bool(shutil.which("tesseract"))
    if have_poppler and have_tesseract:
        _print(OK, "OCR tools present (scanned PDFs supported)")
    else:
        missing = []
        if not have_poppler:
            missing.append("Poppler")
        if not have_tesseract:
            missing.append("Tesseract")
        _print(WARN, f"{' + '.join(missing)} not found - OCR off. Text PDFs work fine; "
                     "scanned PDFs will have little text.")


def build_demo_if_needed() -> bool:
    """Generate the synthetic demo packet if it's missing."""
    if DEMO_PDF.exists():
        _print(OK, f"Demo packet present: {DEMO_PDF.name}")
        return True
    _print("", "Building demo packet...")
    try:
        subprocess.run(
            [sys.executable, str(ROOT / "examples" / "build_synthetic_packet.py")],
            check=True,
        )
        _print(OK, f"Built demo packet: {DEMO_PDF.name}")
        return True
    except Exception as e:
        _print(FAIL, f"Could not build demo packet: {e}")
        return False


def run_pipeline(pdf: Path) -> int:
    """Run the real end-to-end pipeline and print a friendly summary."""
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%H:%M:%S")
    from realtor_doc_processor import process, llm

    print()
    print("=" * 64)
    print(f"  RUNNING PIPELINE  (provider={llm.provider_name()}, model={llm.active_model()})")
    print(f"  input:  {pdf}")
    print(f"  output: {OUTPUT_DIR}")
    print("=" * 64)

    result = process(pdf_path=pdf, output_dir=OUTPUT_DIR)

    tx = result.packet.transaction_fields
    print()
    print("=" * 64)
    print(f"  DONE - job {result.job_id}")
    print("=" * 64)
    print(f"  Property:        {tx.property_address or '(not detected)'}")
    print(f"  Documents found: {len(result.packet.segments)}")
    review = result.packet.low_confidence_segments()
    if review:
        print(f"  Needs review:    {len(review)} (see _NEEDS_REVIEW.txt)")
    print(f"  Folder:          {result.transaction_folder}")
    print(f"  Summary PDF:     {result.summary_pdf}")
    if result.zip_path:
        print(f"  Zip:             {result.zip_path}")
    print()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", nargs="?", type=Path, help="PDF to process (default: demo packet)")
    ap.add_argument("--check", action="store_true", help="Only run environment checks")
    args = ap.parse_args()

    load_dotenv()

    print("\nRealtor Document Processor - environment check\n" + "-" * 46)
    deps_ok = check_python_deps()
    ai_ok, _ = check_ai_provider()
    check_optional_ocr()

    hard_ok = deps_ok and ai_ok

    if args.check:
        print()
        print("Environment looks ready." if hard_ok else "Environment NOT ready - see [FAIL] above.")
        return 0 if hard_ok else 1

    if not hard_ok:
        print("\nCannot run the pipeline until the [FAIL] items above are fixed.")
        return 1

    pdf = args.pdf
    if pdf is None:
        if not build_demo_if_needed():
            return 1
        pdf = DEMO_PDF
    elif not pdf.exists():
        _print(FAIL, f"Input PDF not found: {pdf}")
        return 1

    return run_pipeline(pdf)


if __name__ == "__main__":
    sys.exit(main())
