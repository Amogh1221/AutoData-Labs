# AutoData Labs

> **Turn any research topic into a structured, exportable dataset — fully automated, runs 100% offline with Ollama.**

AutoData Labs is an autonomous multi-agent data extraction system. You describe what you want to research; a pipeline of specialized AI agents builds the schema, discovers real web sources, scrapes and extracts structured rows, fills in missing values, and streams results to a live dashboard — all without you lifting a finger.

---

## ✨ Features

- 🧠 **Planner Agent** — Generates a column schema tailored to your topic using LLM + live DuckDuckGo context
- 🔍 **Source Agent** — Discovers real URLs via web search and classifies them (HTML page, CSV, JSON API)
- 📄 **Research Agent** — Crawls each source with Playwright, chunks content, and extracts structured rows via LLM
- ✅ **Completion Agent** — Audits extracted rows for missing fields and fills them with targeted follow-up searches
- ⚡ **Real-time streaming** — Each extracted row appears in the dashboard the moment it's saved (SSE + 1 s polling)
- ⏹️ **Instant stop / pause / resume** — Pipeline responds to control commands within ~1 second
- 🔑 **API key exhaustion handling** — Mid-run popup lets users supply their own key to resume; partial data is always exportable
- 🌐 **Cloud mode** — Switch from Ollama to Groq (free) or Hugging Face via a single env var
- 📦 **CSV export** — Download the complete dataset at any point

---

## 🏗️ Architecture

```
User → Planner Agent → Schema
     → Source Agent → URL Queue → Research Agent → SQLite → Completion Agent
                                                          ↕
                                                    Frontend (SSE stream)
```

See [architecture.md](./architecture.md) for the full technical breakdown and data-flow diagram.

---

## 🚀 Getting Started

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | ≥ 3.11 | Backend runtime |
| Node.js | ≥ 18 | Frontend build |
| Ollama | Latest | Local LLM inference (offline mode) |
| Playwright | Bundled | JavaScript-rendered page crawling |

### 1 — Clone & install backend

```bash
git clone https://github.com/Amogh1221/AutoData-Labs.git
cd AutoData-Labs

# Create virtual environment
python -m venv .data
.data\Scripts\activate        # Windows
# source .data/bin/activate   # macOS/Linux

pip install -r requirements.txt
playwright install chromium
```

### 2 — Pull the local model (offline mode)

```bash
ollama pull qwen2.5:7b-instruct
```

### 3 — Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# --- Offline (default) ---
OLLAMA_MODEL=qwen2.5:7b-instruct
CLOUD_MODE=false

# --- Cloud (optional) ---
# CLOUD_MODE=true
# CLOUD_PROVIDER=groq             # 'groq' (free) or 'hf'
# GROQ_API_KEY=gsk_...            # Free key: https://console.groq.com
# GROQ_MODEL=llama-3.1-8b-instant
```

### 4 — Start the backend

```bash
python -m uvicorn main:app --reload --port 8000
```

### 5 — Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open **[http://localhost:5173](http://localhost:5173)**

---

## 🖥️ Usage

1. **Enter a topic** — e.g. `"AI startups in India"` or `"Michelin-starred restaurants in Paris"`
2. **Review the schema** — the Planner Agent suggests columns; add, remove, or rename them
3. **Start extraction** — agents run autonomously; rows appear in the table as they're extracted
4. **Monitor the dashboard** — live agent status, analytics charts, and a full log trace
5. **Export** — download the dataset as CSV at any time, even mid-run

---

## ⚙️ Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `CLOUD_MODE` | `false` | `true` = use cloud LLM; `false` = use local Ollama |
| `CLOUD_PROVIDER` | `groq` | Cloud backend: `groq` or `hf` |
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct` | Ollama model name |
| `GROQ_API_KEY` | — | Free key from [console.groq.com](https://console.groq.com) |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Groq model ID |
| `HF_API_KEY` | — | HuggingFace token (when `CLOUD_PROVIDER=hf`) |
| `HF_MODEL` | `meta-llama/Llama-3.1-8B-Instruct` | HuggingFace model ID |
| `HF_PROVIDER` | `nebius` | HF router provider (`nebius`, `hf-inference`) |

---

## 🗂️ Project Structure

```
AutoData Labs/
├── main.py                    # FastAPI app entrypoint
├── requirements.txt
├── .env.example
│
├── core/                      # Shared domain layer
│   ├── llm.py                 # Unified LLM interface (Ollama / Groq / HF)
│   ├── models.py              # Internal dataclasses (Entity, RunLog, Source)
│   ├── schemas.py             # Pydantic API request/response models
│   ├── interfaces.py          # Abstract interfaces (ISearchProvider, ICrawlProvider)
│   └── prompts.py             # All LLM prompt templates
│
├── services/                  # Business logic (agent implementations)
│   ├── planner_service.py     # Schema generation & column validation
│   ├── source_service.py      # URL discovery & classification
│   ├── research_service.py    # Crawl → chunk → extract → save (streaming)
│   └── completion_service.py  # Missing-field gap-filling
│
├── providers/                 # Pluggable infrastructure adapters
│   ├── ddg_search_provider.py        # DuckDuckGo search
│   ├── playwright_crawl_provider.py  # JS-rendered page crawler
│   ├── bs4_crawl_provider.py         # Static HTML fallback
│   └── ollama_extractor.py           # Legacy direct-Ollama extractor
│
├── api/
│   ├── routes.py              # All HTTP endpoints + pipeline orchestration
│   └── dependencies.py        # FastAPI dependency injection container
│
├── persistence/
│   └── sqlite_store.py        # SQLite read/write for entities, sources, logs
│
├── tests/
│   └── test_llm.py            # Unit tests for core/llm.py
│
└── frontend/                  # React + Vite dashboard
    └── src/
        └── pages/
            ├── Home.jsx        # Topic input + schema builder
            └── Dashboard.jsx  # Live extraction monitor + data table
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Python 3.11+ |
| LLM (local) | Ollama (`qwen2.5:7b-instruct`) |
| LLM (cloud) | Groq API / Hugging Face Inference API |
| Web crawling | Playwright (JS), BeautifulSoup (static) |
| Search | DuckDuckGo (`ddgs`) |
| Database | SQLite (via `sqlite3`) |
| Streaming | Server-Sent Events (SSE) |
| Frontend | React 18, Vite, Recharts |

---

## 🧪 Running Tests

```bash
pytest tests/ -v
```

---

## 📝 License

MIT
