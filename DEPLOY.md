# Deploy

Two pieces:

- **Backend** → Hugging Face Spaces (Docker). Does the PDF processing.
- **Frontend** → Vercel (Next.js). The page people use.

---

## 1. Backend on Hugging Face Spaces

1. Create a new **Space** → **Docker** (blank template).
2. Push this repository to the Space (the root `Dockerfile` builds it).
3. Make sure the Space's **README.md** starts with this frontmatter so HF serves
   the container on the right port:

   ```yaml
   ---
   title: Realtor Doc Processor API
   emoji: 📄
   colorFrom: indigo
   colorTo: blue
   sdk: docker
   app_port: 7860
   ---
   ```

4. In **Settings → Variables and secrets** add:
   - `GROQ_API_KEY` = your Groq key (free at https://console.groq.com/keys)
   - `ALLOWED_ORIGINS` = your Vercel URL, e.g. `https://your-app.vercel.app`
     (use `*` while testing)

5. The Space builds and exposes:
   - `GET  https://<your-space>.hf.space/api/health`
   - `POST https://<your-space>.hf.space/api/process`
   - `GET  https://<your-space>.hf.space/api/download/{jobId}`

Test it: open `…/api/health` in a browser — you should see
`{"ok":true,"configured":true,...}`.

---

## 2. Frontend on Vercel

1. Import this repo into Vercel.
2. **Root Directory** → `frontend`.
3. Framework preset: **Next.js** (auto-detected).
4. **Environment Variables**:
   - `NEXT_PUBLIC_API_URL` = your HF Space URL (no trailing slash), e.g.
     `https://your-space.hf.space`
5. Deploy.

That's it. The page loads, shows "Engine ready", and uploads go straight to the
HF backend.

---

## Local development

```bash
# Backend (terminal 1) — needs GROQ_API_KEY in .env at repo root
pip install -r requirements.txt && pip install -e .
uvicorn backend.main:app --reload --port 7860

# Frontend (terminal 2)
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://127.0.0.1:7860" > .env.local
npm run dev        # http://localhost:3000
```

## Notes

- Output zips are written to a temp dir in the container and are **ephemeral**
  (fine for download-now). For permanent storage, push the zip to object
  storage (e.g. Supabase/S3) in `backend/main.py` after `process(...)`.
- Provider/model are env-driven: `AI_PROVIDER` (groq | openrouter | openai),
  `AI_MODEL`, and the matching `*_API_KEY`. See `.env.example`.
