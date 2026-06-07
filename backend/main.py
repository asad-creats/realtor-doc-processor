"""
FastAPI backend for the Realtor Document Processor.

Deployed as a Docker Space on Hugging Face (port 7860). The Next.js frontend
(on Vercel) calls these JSON endpoints.

Endpoints:
    GET  /api/health           - status + which model/provider is active
    POST /api/process          - upload a PDF, get back the parsed result
    GET  /api/download/{job}   - download the organized zip for a job
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# ── Load .env for local dev (no-op in cloud where env vars are set directly) ──
def _load_dotenv() -> None:
    env_file = Path(__file__).resolve().parent.parent / ".env"
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


_load_dotenv()

from realtor_doc_processor import process, llm  # noqa: E402

app = FastAPI(title="Realtor Document Processor API", version="1.0.0")

# CORS: allow the Vercel frontend. Set ALLOWED_ORIGINS to a comma-separated
# list in production (e.g. "https://your-app.vercel.app"); "*" by default.
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Where job output lives. Ephemeral on most hosts — fine for download-then-go.
JOBS_DIR = Path(os.getenv("JOBS_DIR", tempfile.gettempdir())) / "rdp_jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

MAX_BYTES = int(os.getenv("MAX_UPLOAD_MB", "100")) * 1024 * 1024


def _safe_name(name: str) -> str:
    base = os.path.basename(name or "packet.pdf")
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip("._") or "packet.pdf"
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    return base


@app.get("/")
def root():
    return {"service": "realtor-doc-processor", "docs": "/docs", "health": "/api/health"}


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "configured": llm.is_configured(),
        "provider": llm.provider_name(),
        "model": llm.active_model(),
    }


@app.post("/api/process")
def process_endpoint(file: UploadFile = File(...)):
    if not llm.is_configured():
        raise HTTPException(
            status_code=503,
            detail=f"AI provider '{llm.provider_name()}' is not configured. "
                   f"Set {llm.provider_name().upper()}_API_KEY on the server.",
        )
    if file.content_type and "pdf" not in file.content_type.lower() \
            and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file.")

    job_id = uuid.uuid4().hex[:12]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    saved = job_dir / _safe_name(file.filename)
    size = 0
    with saved.open("wb") as out:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_BYTES:
                shutil.rmtree(job_dir, ignore_errors=True)
                raise HTTPException(status_code=413,
                                    detail=f"File exceeds {MAX_BYTES // (1024*1024)} MB limit.")
            out.write(chunk)

    try:
        result = process(pdf_path=saved, output_dir=job_dir, job_id=job_id)
    except Exception as e:  # surface a clean message to the UI
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")

    tx = result.packet.transaction_fields
    out_files = sorted(
        p.name for p in result.transaction_folder.iterdir()
        if p.is_file() and not p.name.endswith(".zip")
    )
    return {
        "ok": True,
        "jobId": job_id,
        "address": tx.property_address,
        "buyers": tx.buyer_names,
        "sellers": tx.seller_names,
        "purchasePrice": tx.purchase_price,
        "earnestMoney": tx.earnest_money,
        "contractDate": tx.contract_date,
        "closeDate": tx.close_of_escrow_date,
        "escrowNumber": tx.escrow_number,
        "mlsNumber": tx.mls_number,
        "listingAgent": tx.listing_agent,
        "buyersAgent": tx.buyers_agent,
        "documents": [
            {
                "code": s.doc_type_code,
                "startPage": s.start_page,
                "endPage": s.end_page,
                "confidence": round(s.confidence, 2),
                "needsReview": s.needs_review or s.confidence < 0.75,
            }
            for s in result.packet.segments
        ],
        "docCount": len(result.packet.segments),
        "needsReview": len(result.packet.low_confidence_segments()),
        "files": out_files,
        "downloadUrl": f"/api/download/{job_id}",
    }


@app.get("/api/download/{job_id}")
def download(job_id: str):
    job_id = re.sub(r"[^a-f0-9]", "", job_id)[:12]
    job_dir = JOBS_DIR / job_id
    zips = list(job_dir.glob("*.zip")) if job_dir.exists() else []
    if not zips:
        raise HTTPException(status_code=404, detail="Result not found or expired.")
    zip_path = zips[0]
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)
