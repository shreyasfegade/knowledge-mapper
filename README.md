# Knowledge Mapper

**Upload educational content to generate interactive conceptual knowledge graphs.** Force-directed visuals powered by LLM relationship inference.

![Next.js](https://img.shields.io/badge/Next.js-000000?style=flat-square&logo=nextdotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Cytoscape.js](https://img.shields.io/badge/Cytoscape.js-F7DF1E?style=flat-square&logo=javascript&logoColor=black)
![DeepSeek](https://img.shields.io/badge/DeepSeek_API-4B0082?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## The Problem

Standard document search and "chat with PDF" tools present information sequentially or through conversational prompts. This fails to give a holistic view of the subject, hiding how different concepts interact. When studying complex STEM subjects, understanding *how* concepts connect—such as prerequisites, causations, and dependencies—is critical to building mental models.

## The Solution

**Knowledge Mapper** ingests educational files (PDFs, PPTs), processes them through a pipeline that extracts core concepts, computes their semantic embeddings, and uses a Large Language Model (LLM) to discover prerequisite and causal relationships. The resulting semantic topology is rendered as an interactive, Obsidian-like force-directed graph built with Cytoscape.js.

---

## Features

- **Document Ingestion** — Upload and extract structural text from PDFs and presentations.
- **Concept Extraction Pipeline** — Extracts atomic, high-quality concepts using sentence-level NLP filters and LLM validation.
- **Causal Relationship Inference** — Evaluates concept pairs to map true linkages (prerequisites, causation, and dependencies) rather than simple keyword matches.
- **Interactive Force Graph** — Renders the conceptual graph using Cytoscape.js, featuring Louvain community detection for semantic clustering, node expansion, and dynamic layouts.
- **Semantic Filtering** — Uses Sentence-Transformers to compute cosine similarity, pruning weak relations before LLM evaluation to manage API usage.
- **Real-Time Stream Processing** — Implements Server-Sent Events (SSE) in FastAPI to stream extraction progress (chunking, extraction, similarity checking, mapping) directly to the Next.js frontend.

---

## Tech Stack

- **Frontend**: Next.js 15 (App Router, TypeScript), Tailwind CSS, Cytoscape.js, Zustand
- **Backend**: FastAPI (Python 3.11+), Uvicorn, LangChain
- **Embeddings & NLP**: `sentence-transformers` (local running models), `pandas`, `numpy`
- **LLM Engine**: DeepSeek API (or compatible OpenAI-format providers)

---

## Quick Start

### Prerequisites

- Node.js 18+
- Python 3.11+
- A DeepSeek API Key (free tier available)

### Installation & Run

1. **Clone the repository:**
   ```bash
   git clone https://github.com/shreyasfegade/knowledge-mapper.git
   cd knowledge-mapper
   ```

2. **Configure environment:**
   Create a `.env` file in the `backend/` directory and add your key:
   ```env
   DEEPSEEK_API_KEY=your_api_key_here
   ```

3. **Launch the backend:**
   ```bash
   cd backend
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Mac/Linux:
   source .venv/bin/activate
   
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```

4. **Launch the frontend:**
   Open a separate terminal window:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## Project Structure

```text
knowledge-mapper/
├── .ai-docs/               # Archived original AI specs (ignored by git)
├── backend/                # FastAPI application
│   ├── app/
│   │   ├── main.py         # Entry point and SSE endpoints
│   │   ├── pipeline.py     # Document text ingestion & processing
│   │   ├── extractor.py    # Concept & relationship LLM pipelines
│   │   └── models.py       # Pydantic schemas and database models
│   ├── requirements.txt    # Python packages
│   └── .env.example
├── frontend/               # Next.js application
│   ├── src/
│   │   ├── components/     # Cytoscape graph renderer, upload modules
│   │   └── app/            # App Router pages
│   ├── package.json        # Node.js dependencies
│   └── tailwind.config.js
├── LICENSE                 # MIT License
├── .gitignore              # Git exclusions
└── README.md               # Project documentation
```

---

## Current Status

This project is a **functional experimental prototype**.

- **Implemented**: Multi-page PDF text extraction, Sentence-Transformer semantic filtering, FastAPI SSE stream connection, LLM concept extraction, relationship classification, and Cytoscape force-directed graph UI.
- **In Progress**: Merging multiple uploaded document topologies into a single master conceptual map.
- **Planned**: Graph export capabilities to Markdown-based Obsidian formats.

---

## Architecture

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│   INGESTION     │         │  NLP PIPELINE   │         │    GRAPH UI     │
│                 │         │                 │         │                 │
│ • PDF Upload    │────────►│ • NLTK Tokenize │────────►│ • Cytoscape.js  │
│ • Text Extract  │  pages  │ • tf-idf Rank   │ nodes   │ • Louvain Clust.│
│ • SSE Stream    │  + text │ • MiniLM Embed  │ + edges │ • Force Layout  │
│                 │         │ • DeepSeek LLM  │         │ • Edge Filter   │
└─────────────────┘         └─────────────────┘         └─────────────────┘
```

### Data Flow

```
1. PDF uploaded
   ↓
2. Text extracted page-by-page ────────── ~500ms (PyMuPDF)
   ↓
3. Key terms ranked ───────────────────── ~200ms (NLTK tokenize + tf-idf)
   ↓
4. Concepts extracted via LLM ─────────── ~3s (DeepSeek structured output)
   ↓
5. Embeddings generated ───────────────── ~200ms (all-MiniLM-L6-v2 local)
   ↓
6. Similar pairs filtered ─────────────── ~50ms (cosine > 0.45 threshold)
   ↓
7. Relationships validated via LLM ────── ~5s (only filtered pairs sent)
   ↓
8. Graph rendered ─────────────────────── ~100ms (Cytoscape.js + Louvain)

Total: ~9s from upload to interactive knowledge graph
```

For $N$ concepts, exhaustive pair checking produces $\frac{N(N-1)}{2}$ relationships (435 pairs for 30 concepts). The cosine similarity pre-filter eliminates 75%+ of pairs before they reach the LLM, reducing both latency and API cost.

---

## Limitations

- **API Dependency**: Requires a functional DeepSeek API key for structured relationship reasoning.
- **Process Time**: Ingesting and mapping large documents (>50 pages) takes several minutes due to LLM call queues.
- **STEM Content Focus**: Highly optimized for STEM educational materials; humanities texts with looser prerequisite hierarchies yield simpler maps.

---

## What This Project Taught Me

- How NLP pipeline architectures work: text extraction → embedding → filtering → LLM inference.
- Why local embedding models can drastically reduce API costs through pre-filtering.
- How force-directed graph layouts and community detection algorithms (Louvain) organize complex data visually.
- The architecture of Server-Sent Events (SSE) for real-time streaming between backend and frontend.

## Development Note

**Built with AI-assisted development.** I directed the product vision, designed the pipeline architecture, and made the key technical decisions. AI tools accelerated the implementation.

My contributions:
- The core idea: conceptual knowledge mapping over generic chatbot interfaces for educational content.
- Architecture: the embedding-based pre-filter pipeline to optimize LLM API costs.
- Graph layout direction: force-directed visuals with community clustering for readable concept maps.
- Structuring the Next.js-to-FastAPI SSE streaming configuration.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
