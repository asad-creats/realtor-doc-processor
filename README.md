---
title: Realtor Doc Processor API
emoji: 📄
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Realtor Document Processor

A Python pipeline that takes a real estate transaction packet PDF — combined, messy, or scanned — and produces a properly named, organized folder of individual documents plus a transaction summary PDF.

It classifies and splits each document using a **cloud LLM API** (Groq by default). No GPU, no local model daemon.

It ships as two deployable parts:

- **Backend** — a FastAPI service (Docker) that runs the pipeline. Deploys to **Hugging Face Spaces**.
- **Frontend** — a polished Next.js page where you drop a PDF and download the result. Deploys to **Vercel**.

See **[DEPLOY.md](DEPLOY.md)** for step-by-step deploy instructions.

## What it does

```
Input:  packet.pdf  (a 50-page combined PDF with 8 documents glued together)

Output: 847HillcrestAvenue/
          01_RPA_2026-04-18.pdf
          02_TDS_2026-04-18.pdf
          03_LeadPaint_2026-04-18.pdf
          04_WireInstructions_2026-04-18.pdf
          _TransactionSummary.pdf      ← clean one-page summary
          _summary.json                ← all extracted fields, structured
          _NEEDS_REVIEW.txt            ← flagged segments (if any)
        847HillcrestAvenue.zip
```

## Pipeline stages

1. **Extract** — `pdfplumber` pulls text per page; pages with little text fall back to OCR via `pytesseract` (optional). Text-rich packets need nothing else.
2. **Classify** — Sends page text to the cloud LLM in chunks of ~10 (1-page overlap). The model returns document boundaries, taxonomy codes, confidence scores, and extracted fields as strict JSON.
3. **Split** — `pypdf` writes each segment as its own PDF, named via a configurable pattern.
4. **Summarize** — Renders a clean transaction summary PDF using `reportlab`.
5. **Zip** — Packages the folder for download.

## Run locally

```bash
# 1. Get a free Groq key at https://console.groq.com/keys
#    Copy .env.example to .env and paste it:
#    AI_PROVIDER=groq
#    GROQ_API_KEY=your-key-here

# 2. Backend (terminal 1)
pip install -r requirements.txt && pip install -e .
uvicorn backend.main:app --reload --port 7860

# 3. Frontend (terminal 2)
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://127.0.0.1:7860" > .env.local
npm run dev            # open http://localhost:3000
```

Quick API-only sanity check without the frontend:
```
python quickstart.py            # runs the demo packet through the pipeline
```

## Deploy

See **[DEPLOY.md](DEPLOY.md)** — backend to Hugging Face Spaces, frontend to Vercel.

## Choosing a provider / model

Configured entirely via environment variables (no code changes):

| Var | Default | Notes |
|---|---|---|
| `AI_PROVIDER` | `groq` | `groq`, `openrouter`, or `openai` |
| `AI_MODEL` | per-provider | e.g. `llama-3.3-70b-versatile` (Groq) |
| `GROQ_API_KEY` | — | free tier is plenty for testing |
| `OPENROUTER_API_KEY` / `OPENAI_API_KEY` | — | if using those providers |

Default model `llama-3.3-70b-versatile` (Groq) classifies these text-rich documents extremely well and returns in ~2s.

## Usage (CLI / programmatic)

```
# CLI — process one packet (uses configured provider/model)
process_job C:\Users\You\Downloads\packet.pdf --job-id abc123 --output C:\jobs\done
```

```python
from realtor_doc_processor import process

result = process(pdf_path="packet.pdf", output_dir="./jobs")
print(f"Found {len(result.packet.segments)} documents")
print(f"Property: {result.packet.transaction_fields.property_address}")
print(f"Zip ready at: {result.zip_path}")
```

Filename pattern fields: `{order}`, `{code}`, `{label}`, `{date}`, `{address}`.

## Adding a new document type

Edit `realtor_doc_processor/taxonomy.py` and add a `DocType` entry. The classifier picks it up automatically. Keep the description sharp — it's the main signal the model has.

## Project layout

```
backend/
  main.py                 FastAPI app (HF Spaces) — /api/health, /api/process, /api/download
frontend/
  app/page.tsx            the Next.js page (Vercel) — drag-drop upload + results
  app/layout.tsx, globals.css, tailwind/postcss/ts config
realtor_doc_processor/
  llm.py                  cloud LLM client (Groq/OpenRouter/OpenAI, OpenAI-compatible)
  taxonomy.py             document types
  models.py               dataclasses for jobs/segments/fields
  pdf_extract.py          text + optional OCR/thumbnails
  classifier.py           chunking, LLM calls, JSON parsing
  splitter.py             PDF splitting + filename generation
  template_render.py      summary PDF
  pipeline.py             orchestrates all of the above
Dockerfile                backend image (uvicorn, port 7860)
DEPLOY.md                 HF Spaces + Vercel instructions
.env.example              provider/key configuration
quickstart.py             CLI sanity check
examples/, tests/
```

## Troubleshooting

- **"AI provider not configured" / HTTP 401/503** — set `GROQ_API_KEY` (in `.env` locally, or as a host secret).
- **CORS error in the browser** — set `ALLOWED_ORIGINS` on the backend to your Vercel URL.
- **HTTP 429** — provider rate limit / quota; wait, or switch `AI_PROVIDER`/`AI_MODEL`.
- **Scanned PDF comes back empty** — install Poppler + Tesseract for OCR (optional extra).
- **Wrong classifications** — open `_NEEDS_REVIEW.txt` and the segment's `rationale` in `_summary.json`; sharpen the description in `taxonomy.py`.

