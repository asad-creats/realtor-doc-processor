"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

type DocSeg = {
  code: string;
  startPage: number;
  endPage: number;
  confidence: number;
  needsReview: boolean;
};

type Result = {
  ok: boolean;
  jobId: string;
  address: string | null;
  buyers: string[];
  sellers: string[];
  purchasePrice: number | null;
  contractDate: string | null;
  closeDate: string | null;
  documents: DocSeg[];
  docCount: number;
  needsReview: number;
  files: string[];
  downloadUrl: string;
};

const DOC_LABELS: Record<string, string> = {
  RPA: "Purchase Agreement",
  CounterOffer: "Counter Offer",
  Addendum: "Addendum",
  TDS: "Transfer Disclosure",
  SPQ: "Seller Questionnaire",
  AVID: "Agent Visual Inspection",
  LeadPaint: "Lead-Based Paint",
  NHD: "Natural Hazard Disclosure",
  WireInstructions: "Wire Instructions",
  PrelimTitle: "Preliminary Title",
  EscrowInstructions: "Escrow Instructions",
  CommissionAgreement: "Commission Agreement",
  ListingAgreement: "Listing Agreement",
  BuyerRepAgreement: "Buyer Representation",
  HOA: "HOA Documents",
  InspectionReport: "Inspection Report",
  TermiteReport: "Termite / Pest Report",
  Appraisal: "Appraisal",
  LoanEstimate: "Loan Estimate",
  ClosingDisclosure: "Closing Disclosure",
  ProofOfFunds: "Proof of Funds",
  PreApproval: "Pre-Approval Letter",
  ContingencyRemoval: "Contingency Removal",
  GrantDeed: "Grant Deed",
  OTHER: "Unclassified",
};

const money = (n: number | null) =>
  n == null ? "—" : "$" + n.toLocaleString(undefined, { maximumFractionDigits: 0 });

const fmtDate = (s: string | null) => {
  if (!s) return "—";
  const d = new Date(s + "T00:00:00");
  return isNaN(d.getTime())
    ? s
    : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
};

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState<"idle" | "working" | "done" | "error">("idle");
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string>("");
  const [engine, setEngine] = useState<{ ok: boolean; model?: string; provider?: string } | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!API_BASE) return;
    fetch(`${API_BASE}/api/health`)
      .then((r) => r.json())
      .then((d) => setEngine({ ok: !!d.configured, model: d.model, provider: d.provider }))
      .catch(() => setEngine({ ok: false }));
  }, []);

  const pick = (f: File | null) => {
    if (f && f.type !== "application/pdf" && !f.name.toLowerCase().endsWith(".pdf")) {
      setError("Please choose a PDF file.");
      return;
    }
    setError("");
    setFile(f);
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files?.[0]) pick(e.dataTransfer.files[0]);
  }, []);

  const submit = async () => {
    if (!file) return;
    if (!API_BASE) {
      setError("NEXT_PUBLIC_API_URL is not set. Point it at your Hugging Face Space URL.");
      setStatus("error");
      return;
    }
    setStatus("working");
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch(`${API_BASE}/api/process`, { method: "POST", body: fd });
      const data = await r.json().catch(() => null);
      if (!r.ok || !data?.ok) {
        throw new Error(data?.detail || data?.error || `Request failed (HTTP ${r.status}).`);
      }
      setResult(data as Result);
      setStatus("done");
    } catch (e: any) {
      setError(e?.message || "Something went wrong.");
      setStatus("error");
    }
  };

  const reset = () => {
    setFile(null);
    setResult(null);
    setError("");
    setStatus("idle");
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-white via-slate-50 to-slate-100">
      {/* Nav */}
      <header className="mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm">
            <DocIcon className="h-5 w-5" />
          </div>
          <span className="text-[15px] font-semibold tracking-tight">Packet Organizer</span>
        </div>
        {engine && (
          <span
            className={`hidden items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium sm:inline-flex ${
              engine.ok ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"
            }`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${engine.ok ? "bg-emerald-500" : "bg-amber-500"}`} />
            {engine.ok ? `Engine ready · ${engine.model}` : "Engine not configured"}
          </span>
        )}
      </header>

      <section className="mx-auto max-w-3xl px-6 pb-24 pt-8">
        {/* Hero */}
        <div className="text-center">
          <h1 className="text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">
            Turn one messy packet into a clean deal file
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-base leading-relaxed text-slate-500">
            Drop a combined transaction PDF. We identify each document, split it out, rename it,
            and hand back an organized folder with a transaction summary.
          </p>
        </div>

        {/* Card */}
        <div className="mt-12 rounded-3xl border border-slate-200 bg-white p-6 shadow-xl shadow-slate-200/50 sm:p-8">
          {status !== "done" && (
            <>
              <label
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-14 text-center transition ${
                  dragging
                    ? "border-indigo-400 bg-indigo-50/60"
                    : "border-slate-200 bg-slate-50/60 hover:border-slate-300 hover:bg-slate-50"
                }`}
              >
                <UploadIcon className="mb-3 h-9 w-9 text-indigo-500" />
                <span className="text-[15px] font-semibold text-slate-800">
                  {file ? file.name : "Drag a PDF here, or click to browse"}
                </span>
                <span className="mt-1 text-xs text-slate-400">
                  {file ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : "Combined packets up to 100 MB"}
                </span>
                <input
                  ref={inputRef}
                  type="file"
                  accept="application/pdf"
                  className="hidden"
                  onChange={(e) => pick(e.target.files?.[0] || null)}
                />
              </label>

              <button
                onClick={submit}
                disabled={!file || status === "working"}
                className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3.5 text-[15px] font-semibold text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-indigo-300"
              >
                {status === "working" ? (
                  <>
                    <Spinner className="h-4 w-4 animate-spin" />
                    Processing… this can take a moment
                  </>
                ) : (
                  "Process packet"
                )}
              </button>

              {status === "error" && (
                <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
              )}
            </>
          )}

          {/* Result */}
          {status === "done" && result && (
            <div className="animate-fade-up">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
                  <CheckIcon className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-slate-900">
                    {result.docCount} document{result.docCount === 1 ? "" : "s"} organized
                  </h2>
                  <p className="text-sm text-slate-500">{result.address || "Address not detected"}</p>
                </div>
              </div>

              {/* Summary grid */}
              <dl className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-slate-200 bg-slate-200 sm:grid-cols-4">
                <Stat label="Purchase price" value={money(result.purchasePrice)} />
                <Stat label="Contract date" value={fmtDate(result.contractDate)} />
                <Stat label="Close of escrow" value={fmtDate(result.closeDate)} />
                <Stat
                  label="Needs review"
                  value={result.needsReview ? String(result.needsReview) : "None"}
                  warn={result.needsReview > 0}
                />
              </dl>

              {(result.buyers?.length > 0 || result.sellers?.length > 0) && (
                <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <Party label="Buyer(s)" names={result.buyers} />
                  <Party label="Seller(s)" names={result.sellers} />
                </div>
              )}

              {/* Document list */}
              <ul className="mt-6 divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200">
                {result.documents.map((d, i) => (
                  <li key={i} className="flex items-center justify-between gap-3 px-4 py-3">
                    <div className="flex items-center gap-3">
                      <span className="flex h-7 w-7 flex-none items-center justify-center rounded-lg bg-slate-100 text-xs font-semibold text-slate-500">
                        {i + 1}
                      </span>
                      <div>
                        <p className="text-sm font-medium text-slate-800">
                          {DOC_LABELS[d.code] || d.code}
                        </p>
                        <p className="text-xs text-slate-400">
                          {d.startPage === d.endPage
                            ? `Page ${d.startPage}`
                            : `Pages ${d.startPage}–${d.endPage}`}
                        </p>
                      </div>
                    </div>
                    <ConfidenceBadge value={d.confidence} review={d.needsReview} />
                  </li>
                ))}
              </ul>

              <div className="mt-6 flex flex-col gap-3 sm:flex-row">
                <a
                  href={`${API_BASE}${result.downloadUrl}`}
                  className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3.5 text-[15px] font-semibold text-white shadow-sm transition hover:bg-indigo-700"
                >
                  <DownloadIcon className="h-4 w-4" />
                  Download organized ZIP
                </a>
                <button
                  onClick={reset}
                  className="rounded-xl border border-slate-200 bg-white px-5 py-3.5 text-[15px] font-semibold text-slate-700 transition hover:bg-slate-50"
                >
                  Process another
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Steps */}
        {status !== "done" && (
          <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Step n="1" title="Upload" text="One combined PDF, however messy." />
            <Step n="2" title="AI sorts it" text="Each document is identified and split apart." />
            <Step n="3" title="Download" text="Renamed files + a clean summary, zipped." />
          </div>
        )}
      </section>

      <footer className="border-t border-slate-200/70 py-6 text-center text-xs text-slate-400">
        Realtor Document Processor
      </footer>
    </main>
  );
}

function Stat({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="bg-white px-4 py-3">
      <dt className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className={`mt-0.5 text-sm font-semibold ${warn ? "text-amber-600" : "text-slate-800"}`}>
        {value}
      </dd>
    </div>
  );
}

function Party({ label, names }: { label: string; names: string[] }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-0.5 text-sm font-medium text-slate-800">
        {names?.length ? names.join(", ") : "—"}
      </p>
    </div>
  );
}

function ConfidenceBadge({ value, review }: { value: number; review: boolean }) {
  const pct = Math.round(value * 100);
  const cls = review
    ? "bg-amber-50 text-amber-700"
    : "bg-emerald-50 text-emerald-700";
  return (
    <span className={`flex-none rounded-full px-2.5 py-1 text-xs font-medium ${cls}`}>
      {review ? "Review" : `${pct}%`}
    </span>
  );
}

function Step({ n, title, text }: { n: string; title: string; text: string }) {
  return (
    <div className="rounded-2xl border border-slate-200/70 bg-white/60 p-5">
      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-600">
        {n}
      </div>
      <p className="mt-3 text-sm font-semibold text-slate-800">{title}</p>
      <p className="mt-1 text-sm text-slate-500">{text}</p>
    </div>
  );
}

/* ── Icons (inline, no dependency) ───────────────────────────── */
function DocIcon(p: any) {
  return (
    <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6M9 13h6M9 17h6" />
    </svg>
  );
}
function UploadIcon(p: any) {
  return (
    <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" />
    </svg>
  );
}
function DownloadIcon(p: any) {
  return (
    <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
    </svg>
  );
}
function CheckIcon(p: any) {
  return (
    <svg {...p} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}
function Spinner(p: any) {
  return (
    <svg {...p} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="4" />
      <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}
