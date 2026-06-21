# Knowledge Mapper

**Turn a PDF into an interactive map of how its concepts connect.** Upload educational material; get a force-directed graph of the ideas inside it and the prerequisite, causal, and dependency links between them — inferred by an LLM, not keyword matching.

![Next.js](https://img.shields.io/badge/Next.js_15-000000?style=flat-square&logo=nextdotjs&logoColor=white)
![React](https://img.shields.io/badge/React_19-20232A?style=flat-square&logo=react&logoColor=61DAFB)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![DeepSeek](https://img.shields.io/badge/DeepSeek_API-4B0082?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

![Knowledge Mapper](screenshots/hero.png)

---

## The Problem

"Chat with your PDF" tools answer questions in sequence. They're good at retrieval and bad at structure — they never show you how the ideas in a document fit together. When you're learning a technical subject, the thing you actually need is the shape of it: what's foundational, what depends on what, what causes what. That structure is implicit in the text and invisible in a chat window.

## The Solution

Knowledge Mapper reads a document the way a course designer would, in three passes:

1. **Global understanding** — one LLM pass builds a model of what the document teaches: a summary, its themes, its conceptual domains, the root concepts, and the intended learning flow.
2. **Hierarchical concept extraction** — the text is chunked and processed concurrently; the LLM pulls out teachable concepts (each typed, scored for importance, and tagged with its parent and prerequisites), which are then assembled into an acyclic hierarchy.
3. **Topology inference** — a heuristic scorer ranks concept pairs by cross-domain reach, hierarchy distance, importance, and type complementarity, and sends only the strongest candidates to the LLM in small batches. The model returns directed, typed relationships with a one-line mechanistic justification for each.

The result is rendered as a living, pannable graph on a hand-written canvas: foundational hub concepts anchor the center, domains fan out into sectors, and a force simulation settles the layout and then comes to rest.

---

## Features

- **Three-stage LLM pipeline** — global understanding → hierarchical concept extraction → relationship inference, with deterministic scaffolding (dedup, ID resolution, cycle-breaking, edge-capping) around every model call so the output is structured, not hallucinated soup.
- **12 typed relationships** — `prerequisite_of`, `causes`, `depends_on`, `enables`, `specializes`, `derived_from`, and more — each directed and each carrying the model's reasoning, viewable in the concept panel.
- **Interactive canvas** — a custom 2D renderer with a force-directed simulation, spatial-hash hit testing, momentum panning, zoom/fit, and node focus that dims everything but a concept's neighbors. No graph library; ~114 kB first load.
- **Live progress streaming** — Server-Sent Events report each stage (understanding, chunk N/M, topology batch N/M) as it happens.
- **Persistent, shareable graphs** — every processed document is saved to SQLite. A graph survives a refresh and gets a `?doc=<id>` URL you can share or revisit without re-running the pipeline.
- **Markdown export** — download the map as a single Markdown file with Obsidian-style `[[wikilinks]]`, ready to drop into a vault.
- **⌘K concept search**, **reduced-motion support**, and real loading / empty / error states.

---

## Tech Stack

- **Frontend** — Next.js 15 (App Router) · React 19 · TypeScript · Tailwind CSS · a hand-written `<canvas>` renderer + force simulation (`PhysicsEngine.ts`) and spatial hash (`SpatialIndex.ts`). No Cytoscape, no charting library, no global state library.
- **Backend** — FastAPI · Uvicorn · `sse-starlette` for streaming · SQLite (stdlib) for persistence.
- **Ingestion** — PyMuPDF for PDF text extraction.
- **LLM** — DeepSeek API via the OpenAI SDK (any OpenAI-compatible endpoint works).

There are no embeddings, no NLTK/tf-idf, and no community-detection library — concept and relationship discovery is done entirely by the LLM, with hand-written Python doing the structural bookkeeping.

---

## Quick Start

### Prerequisites

- Node.js 18+
- Python 3.11+
- A DeepSeek API key (free tier works) — or any OpenAI-compatible provider

### 1. Backend

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env          # then edit .env and set DEEPSEEK_API_KEY
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) and drop in a PDF.

---

## Architecture

```
┌──────────────┐     ┌─────────────────────────────────────────────┐     ┌──────────────┐
│   INGESTION  │     │              LLM PIPELINE (async)            │     │   GRAPH UI   │
│              │     │                                              │     │              │
│ • PDF upload │ ──► │ 1. Global understanding   (1 LLM call)       │ ──► │ • Canvas 2D  │
│ • PyMuPDF    │     │ 2. Concept extraction     (chunked, concurrent)│   │ • Force sim  │
│ • Text clean │     │    + hierarchy assembly   (dedup, acyclic)    │   │ • SSE progress│
│              │     │ 3. Topology inference     (scored, batched)   │   │ • Focus/search│
│              │     │    + hub detection + galaxy seed layout       │   │ • MD export   │
└──────────────┘     └─────────────────────────────────────────────┘     └──────────────┘
         │                                  │                                     │
         └──────────────── SQLite persistence (shareable ?doc=id) ───────────────┘
```

### Why scored candidate pairs

Checking every concept pair for a relationship is O(N²) — 30 concepts is 435 pairs, and each pair is an LLM call's worth of reasoning. Instead of sending all of them, the backend scores pairs (cross-domain links and links across hierarchy branches are the interesting ones) and sends only the top `MAX_CANDIDATE_PAIRS` (default 150) in batches of 8. That keeps latency and API cost bounded as documents grow, and biases the graph toward the non-obvious connections worth surfacing.

### Project structure

```text
knowledge-mapper/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app, CORS, lifespan
│   │   ├── config.py               # env-driven settings + tuning knobs
│   │   ├── database.py             # SQLite persistence (graph payloads)
│   │   ├── api/
│   │   │   ├── upload.py           # /upload + background pipeline orchestration
│   │   │   ├── stream.py           # /stream/{job_id} SSE progress
│   │   │   └── documents.py        # /document/{id}, /documents
│   │   └── services/               # one module per pipeline stage
│   │       ├── text_extractor.py   # PyMuPDF extraction
│   │       ├── text_cleaner.py     # artifact/normalization cleanup
│   │       ├── global_understanding.py
│   │       ├── concept_extractor.py
│   │       ├── hierarchy_assembly.py
│   │       ├── topology_inference.py
│   │       ├── graph_transformer.py  # galaxy layout + Cytoscape-style payload
│   │       └── deepseek_client.py
│   └── requirements.txt
├── frontend/
│   ├── app/                        # App Router pages + global styles
│   ├── components/
│   │   ├── canvas/                 # KnowledgeCanvas, PhysicsEngine, SpatialIndex
│   │   ├── panels/                 # Upload, Concept, Search
│   │   └── hud/                    # on-canvas controls
│   └── lib/                        # api client + Markdown export
└── README.md
```

---

## Limitations

- **Needs an API key.** All concept and relationship discovery is LLM-driven; there's no offline mode.
- **Cost and latency scale with concepts.** A short PDF maps in ~10–30s. Large documents (50+ pages) take longer because more chunks and relationship batches go to the LLM. Hard caps (pages, chunks, concepts, pairs, edges) keep this bounded and are configurable in `config.py`.
- **Text PDFs only.** Scanned or image-only PDFs yield no text and are rejected; there's no OCR. PPT and other formats are out of scope.
- **Single document.** Each upload is mapped independently — there's no cross-document merge.
- **STEM-leaning.** The prompts are tuned for material with real prerequisite structure; loosely-structured humanities texts produce sparser maps.
- **Single-process state.** In-flight jobs live in memory (finished graphs are persisted); horizontal scaling would need a shared store like Redis.

---

## A note on building this

The genuinely hard part wasn't calling the model — it was making the model's output *structural and trustworthy*. Most of the backend is the deterministic scaffolding around the LLM: deduplicating concepts across overlapping chunks, resolving free-text parent/prerequisite labels into IDs, breaking cycles so the hierarchy stays acyclic, and capping edges so hub concepts don't turn the graph into hairball. The other interesting piece was the renderer — a from-scratch canvas force simulation that settles and then freezes (instead of spinning the CPU forever), so a 200-node graph idles at rest. This was built with AI assistance on the implementation; the pipeline design, the structural-validation approach, and the rendering decisions are the parts worth pointing at.

## License

MIT — see [LICENSE](LICENSE).
