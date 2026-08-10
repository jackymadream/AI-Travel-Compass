# 🧭 AI Travel Compass – Multi-lingual Hybrid RAG Engine

> An enterprise-grade AI travel recommendation engine combining **Deterministic SQL Filtering** and **Vector Semantic Search (Hybrid RAG)** with strict **TDD Enforcement**.

Project Status
Python Version
FastAPI
Next.js
License

---

## 📌 System Architecture & Hybrid RAG Flow

The application solves the limitations of pure semantic search by combining **hard constraint SQL filtering** with **768-d vector semantic similarity**.

[ User Natural Language Query ] 

▼  

 Query Decomposition │ (Intent Extraction) 

▼  

┌──────────┴───────────────────┐ 

▼                                                                             ▼ 

[ Supabase PostgreSQL ]                           [ Qdrant Vector DB ] 

(Budget, Safety, RLS)                            (Vertex AI 768-d Embeddings)  

└──────────┬───────────────────┘

▼  

 │ Reciprocal Rank │ (Score Combination & Re-ranking) │ Fusion (RRF) Engine │ 

▼  

[ Final Recommendations ] (Localized: EN / ZH-HK / JA)

---



## 🛠️ Tech Stack & Infrastructure

- **AI & Vector Pipeline:** Google Cloud Vertex AI (`text-embedding-004`), Qdrant Cloud Vector Store
- **Backend:** FastAPI, Pydantic v2, Pytest (Strict Red-Green TDD Workflow)
- **Database:** Supabase (PostgreSQL with Row Level Security & Multi-lingual JSONB Schemas)
- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS, Shadcn UI

---



## 🚀 Key Features & Roadmap

- [x] **Phase 1: Foundation & Data Infrastructure**
  - [x] Supabase PostgreSQL setup with RLS policies and multi-lingual schemas.
  - [x] Qdrant 768-d vector collection indexing with Vertex AI embeddings.
  - [x] TDD API endpoint (`/api/v1/countries`) with 100% pytest coverage.
  - [x] Next.js 14 dynamic Explore page with real-time budget & safety sliders.
- [ ] **Phase 2: Hybrid RAG Search Engine (In Active Progress)**
  - [x] Query parsing & intent extraction models (`src/schemas/search.py`).
  - [ ] Two-stage SQL + Vector execution pipeline (`/api/v1/search`).
  - [ ] Frontend AI Natural Language Search Bar.
- [ ] **Phase 3: Agentic Itinerary Planner**
  - [ ] Multi-day route optimization agent with memory.

---



## 💻 Local Development Setup



### Prerequisites

- Python 3.11+
- Node.js 18+
- Supabase & Qdrant Cloud API Accounts



### Quick Start

```bash
# 1. Clone the repository
git clone [https://github.com/YOUR_GITHUB_USERNAME/ai-travel-compass.git](https://github.com/YOUR_GITHUB_USERNAME/ai-travel-compass.git)
cd ai-travel-compass

# 2. Setup Backend Dependencies & Run Tests
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
pytest  # Run TDD test suite

# 3. Setup Frontend
cd frontend
npm install
npm run dev
```



## 📧 Contact & Code Access

This repository is currently under **Active Development**. For live local demos, architectural walkthroughs, or code reviews for technical interviews, please contact:

- **Developer:** Jacky Ma (MA KA YAU)
- **Email:** [jackyma.dream@gmail.com](mailto:jackyma.dream@gmail.com)
- **LinkedIn:** [linkedin.com/in/jacky-ma-546062370](https://www.linkedin.com/in/jacky-ma-546062370/)

