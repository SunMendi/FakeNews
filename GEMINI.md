# Project: Fake News Detector (MVP)

## Project Overview
This project is an MVP backend for a fake news detection platform built with Django and PostgreSQL. Its primary goal is to help users verify claims as true, false, or uncertain through a combination of automated analysis and community-driven fact-checking.

## Key Technologies
*   **Backend:** Django 6.0.2 + DRF
*   **Database:** PostgreSQL + PGVector (for semantic search)
*   **AI/LLM:** 3-Tier Failover System (Gemini 2.5 Flash, Groq/Llama 3.3, OpenRouter)
*   **Embeddings:** `paraphrase-multilingual-MiniLM-L12-v2` (Sentence-Transformers)
*   **Scraping:** `newspaper4k` + `feedparser`

## Architecture Highlights
*   **AI Query Refinement:** Automatically translates Banglish/Bengali to Standard English/Bengali and removes conversational noise before searching.
*   **2-Stage Verification Pipeline:**
    1.  **Recall:** Hybrid retrieval using Keyword + Vector search (PGVector) to find candidate articles.
    2.  **Precision:** Semantic Judge (LLM) analyzes the top 3 articles to produce a final verdict and contextual explanation.
*   **Resilient LLM Failover:** Automated 3-tier chain (Gemini -> Groq -> OpenRouter) to handle rate limits (429) or provider downtime.
*   **Lazy Result Caching:** 
    - AI verdicts and explanations are persisted in the `Claim` model.
    - Contextual summaries are cached in the `Article` model.
    - Subsequent identical searches are served instantly from the database.

## Building and Running
1.  **Setup Environment:**
    ```bash
    source .venv/bin/activate
    pip install -r requirements.txt
    ```
2.  **Migrations:**
    ```bash
    python core/manage.py migrate
    ```
3.  **Fetch News:**
    ```bash
    python core/manage.py fetch_news
    ```
4.  **Run Server:**
    ```bash
    python core/manage.py runserver
    ```

## Core Workflows
### Search & Verification
- **Input:** Raw query (Banglish/English/Bengali).
- **Process:** `refine_query` -> `hybrid_search` -> `build_verdict` (Semantic Judge).
- **Caching:** Hits `Claim` cache first; if missing, triggers AI pipeline and persists results.

### News Ingestion
- `fetch_news` command parses RSS feeds, cleans full-page text with `newspaper4k`, and generates PGVector embeddings for semantic retrieval.

## Development Conventions
*   **LLM Logic:** All AI interactions must pass through `claims.services.llm.FailoverLLM` for resilience.
*   **Vector Search:** Always use refined queries for embedding generation to ensure cross-lingual accuracy.
*   **Testing:** New search logic must be verified with both standard Bengali and Banglish queries.

## Commit Guidelines
*   Format: `type(scope): summary` (e.g., `feat(claims): add LLM failover logic`).
*   Keep commits focused and migration-safe.
