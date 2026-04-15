# Intelligent SQL Agent

## Stack

- Python 3.11+, LangGraph StateGraph, FastAPI, SQLAlchemy, Pydantic Settings
- LLM: Ollama `llama3.2:3b` (local, Dockerized) — swap via `.env` `OLLAMA_MODEL`
- DB: PostgreSQL 16 (Dockerized, seeded e-commerce schema)
- Docker Compose: 3 services — app, postgres, ollama

## Architecture

```
ENTRY → AGENT → VALIDATE → EXECUTE → OBSERVE → REFLECT → END
                ↓ invalid      ↓ HITL pause       ↓ error
              AGENT(retry)  /query/approve     AGENT(retry)
```

- Single agent, single StateGraph. No multi-agent orchestration.
- `AgentState` TypedDict lives in `src/agent/state.py`.
- HITL: `interrupt_before=["execute"]` in `.compile()` — always requires `MemorySaver` checkpointer.
- Session memory: `MemorySaver` (in-memory only, state lost on restart — do not add Redis).
- Every `graph.invoke()` must pass `config={"configurable": {"thread_id": session_id}}`.

## Hard constraints

| Constraint | Why |
|---|---|
| 5 tables max (customers, products, orders, order_items, reviews) | Scope boundary |
| Read-only DB user for all queries | Safety |
| No ORM for data queries — SQLAlchemy `inspect()` only, `text()` for execution | Architecture decision |
| Validate node blocks all DDL/DML | Security |
| Hard limits: iterations=10, retries=2, rows=100, timeout=30s, cache=128 | Resource protection |
| No auth, no Web UI, no Redis, no migration framework | Scope boundary |
| `ChatOllama` from `langchain-ollama`, never `ChatOpenAI` | Stack choice |
| Conversation history truncated to 20 messages before LLM call | Context window |

## Must-know patterns

**Schema description dict** (`src/agent/prompts/schema_desc.py`) is mandatory — the LLM needs plain-English table/column descriptions beyond DDL. Do not skip this.

**Few-shot examples** (`src/agent/prompts/sql_few_shot.py`) — 5-8 NL→SQL pairs required for the 3b model to generate decent SQL.

**Error classes** — exactly 4: `syntax`, `permission`, `timeout`, `no_results` (plus `unknown`). Do not add more.

**Conditional edges** — use named functions, not lambdas. Required for testability.

**ToolNode** — must set `handle_tool_errors=True` (GitHub langchain-ai/langgraph#7412).

**Node names** — must be unique, avoid common prefixes (GitHub langchain-ai/langgraph#6924).

**Ollama health check** — app container polls `http://ollama:11434/api/tags` every 5s for 60s before starting uvicorn (`scripts/app-entrypoint.sh`).

**Postgres init** — schema.sql and seed.sql mount to `/docker-entrypoint-initdb.d/` for auto-execution on first start.

**Model pull** — `scripts/ollama-init.sh` runs `ollama pull llama3.2:3b` on first Docker start.

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | DB + Ollama connectivity |
| POST | `/query` | Main query (returns results or `pending_approval`) |
| POST | `/query/approve` | Resume HITL-interrupted query |
| POST | `/query/stream` | SSE streaming of node events |
| GET | `/schema` | Table/column info with descriptions |
| GET | `/history/{session_id}` | Conversation history |

## Dev commands

```bash
docker-compose up -d                          # Start all services
docker-compose config                          # Validate compose file
curl http://localhost:8000/health              # Health check
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "show me all customers", "session_id": "test"}'
```

## Config

All config via `src/config/settings.py` (Pydantic BaseSettings) + `.env` file. Key overrides:

```
OLLAMA_MODEL=llama3.2:3b          # Swap model here
LANGCHAIN_TRACING_V2=false        # Enable LangSmith
LANGCHAIN_API_KEY=                 # LangSmith key
```

## Verification

No test framework. All verification is agent-executed QA scenarios (curl against FastAPI, docker-compose smoke tests). Evidence saved to `.sisyphus/evidence/task-{N}-{slug}.{ext}`.