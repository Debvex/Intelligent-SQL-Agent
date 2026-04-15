# Intelligent SQL Agent

A fully-dockerized, FastAPI-powered intelligent SQL agent built with LangGraph's StateGraph that translates natural language to validated SQL, executes it against a seeded PostgreSQL e-commerce database, and returns results — with human-in-the-loop approval, error recovery, session memory, and LangSmith observability.

**Purpose**: Project-based learning — learn agentic AI, graph-based workflows, and database interaction patterns.

## Stack

- **Language**: Python 3.11+
- **Agent Framework**: LangGraph (StateGraph with TypedDict state)
- **API**: FastAPI (async REST endpoints)
- **DB Access**: SQLAlchemy `inspect()` for schema introspection + `text()` for raw SQL execution
- **LLM**: Ollama `llama3.2:3b` (local, Dockerized) — model swappable via `.env`
- **DB**: PostgreSQL 16 (Dockerized, seeded e-commerce schema)
- **Config**: Pydantic BaseSettings + `.env` file
- **Observability**: LangSmith tracing (optional, free tier)
- **Containerization**: Docker Compose — 3 services: `app`, `postgres`, `ollama`

## Architecture

### Graph topology

```
ENTRY → AGENT → VALIDATE → EXECUTE → OBSERVE → REFLECT → END
                ↓ invalid      ↓ HITL pause       ↓ error
              AGENT(retry)  /query/approve     AGENT(retry)
```

- Single agent, single StateGraph. No multi-agent orchestration.
- 5 nodes with conditional edges: `agent`, `validate`, `execute`, `observe`, `reflect`.
- `AgentState` TypedDict lives in `src/agent/state.py`.
- HITL: `interrupt_before=["execute"]` in `.compile()` — always requires `MemorySaver` checkpointer.
- Session memory: `MemorySaver` (in-memory only, state lost on restart — do not add Redis).
- Every `graph.invoke()` must pass `config={"configurable": {"thread_id": session_id}}`.

### How the pipeline works

1. **AGENT** — LLM (ChatOllama) receives the user's natural language query + conversation history (last 20 messages) + schema context + few-shot examples. It either generates SQL (tool call) or responds conversationally. Binds SQL tools via `.bind_tools()`.
2. **VALIDATE** — Checks the generated SQL: must be SELECT-only (blocks DDL/DML), no injection patterns, referenced tables must exist in schema, reasonable length. Sets `validation_result.is_valid` and routes accordingly.
3. **EXECUTE** — If validation passed and HITL approved, runs the SQL against PostgreSQL via `execute_query()` tool. Applies row limit cap (100), query timeout (30s). Classifies errors: `syntax`, `permission`, `timeout`, `no_results`.
4. **OBSERVE** — Formats query results for human consumption: markdown table for small results, summary sentence for aggregates, "No results found" for empty sets. Adds `AIMessage` to conversation history.
5. **REFLECT** — Decides next step: success → END, error with retries left → back to AGENT with error context, retries exhausted → END with failure message.

### Human-in-the-loop flow

1. User sends query via `POST /query`
2. Graph runs AGENT → VALIDATE, then pauses before EXECUTE (`interrupt_before`)
3. API returns `{status: "pending_approval", proposed_sql: "...", request_id: "..."}`
4. User reviews the SQL and calls `POST /query/approve` with `approved: true/false`
5. If approved: graph resumes from EXECUTE → OBSERVE → REFLECT → END
6. If rejected: API returns `{status: "rejected"}`, no SQL executed

## Folder structure

```
Intelligent SQL Agent/
├── docker-compose.yml            # 3 services: app, postgres, ollama
├── Dockerfile                    # Multi-stage Python build, non-root user
├── .dockerignore                 # Exclude .git, .venv, __pycache__, .env
├── .env.example                  # All config vars with defaults + comments
├── .env                          # Local overrides (gitignored)
├── .gitignore                    # Python, Docker, IDE, .env, __pycache__
├── pyproject.toml                # Project metadata + dependency declarations
├── requirements.txt              # Pinned versions
│
├── scripts/
│   ├── model_spike.py            # Task 0: validate llama3.2:3b SQL quality (5 test queries)
│   ├── ollama-init.sh            # Pull llama3.2:3b on first Docker start
│   └── app-entrypoint.sh         # Poll Ollama readiness then start uvicorn
│
└── src/
    ├── __init__.py
    ├── main.py                   # FastAPI app entrypoint (uvicorn src.main:app)
    │
    ├── config/
    │   ├── __init__.py
    │   └── settings.py           # Pydantic BaseSettings — all config from .env
    │
    ├── api/
    │   ├── __init__.py
    │   ├── app.py                 # FastAPI instance, CORS, lifespan, router includes
    │   └── routes/
    │       ├── __init__.py
    │       ├── health.py          # GET /health — DB + Ollama connectivity check
    │       ├── query.py           # POST /query — main query endpoint, cache check, graph invoke
    │       ├── approve.py         # POST /query/approve — resume HITL-interrupted graph
    │       ├── stream.py          # POST /query/stream — SSE of node-by-node events
    │       ├── schema.py          # GET /schema — all tables with columns + descriptions
    │       └── history.py        # GET /history/{session_id} — conversation from checkpointer
    │
    ├── agent/
    │   ├── __init__.py
    │   ├── graph.py               # StateGraph: node definitions, edges, compile with MemorySaver
    │   ├── state.py               # AgentState TypedDict (messages, query, sql, results, errors, etc.)
    │   ├── cache.py               # QueryCache — in-memory LRU, keyed by (session_id, normalized_query)
    │   ├── error_handlers.py      # classify_error(), should_retry(), build_retry_message() — 4 error classes
    │   ├── tracing.py             # LangSmith setup — sets env vars if LANGCHAIN_TRACING_V2=true
    │   │
    │   ├── nodes/
    │   │   ├── __init__.py
    │   │   ├── agent.py           # AGENT node — ChatOllama LLM call, tool binding, decides SQL or conversation
    │   │   ├── validate.py       # VALIDATE node — SQL safety checks, block DDL/DML/injection, table existence
    │   │   ├── execute.py        # EXECUTE node — run SQL via execute_query(), error classification, HITL check
    │   │   ├── observe.py        # OBSERVE node — format results as markdown table or summary sentence
    │   │   └── reflect.py       # REFLECT node — retry decision, error context injection, iteration/retry limits
    │   │
    │   ├── tools/
    │   │   ├── __init__.py
    │   │   └── sql_tools.py      # @tool functions: get_schema_info(), execute_query()
    │   │
    │   └── prompts/
    │       ├── __init__.py
    │       ├── system.py          # System prompt — SQL-only instructions, role definition
    │       ├── sql_few_shot.py   # 5-8 NL→SQL example pairs for in-context learning
    │       └── schema_desc.py    # Human-written dict: table/column descriptions (mandatory for LLM)
    │
    └── db/
        ├── __init__.py
        ├── connection.py          # SQLAlchemy sync engine, connection pool, context manager
        ├── schema.sql             # DDL — 5 tables, FKs, ENUMs, indexes, readonly_user grant
        └── seed.sql               # Realistic data — 20+ customers, 15+ products, 30+ orders, etc.
```

## Functionalities by module

### `src/config/` — Configuration
- `settings.py`: Single `Settings` class (Pydantic BaseSettings) loading from `.env`. Holds every tunable: DB credentials, Ollama URL/model, hard limits (iterations, retries, rows, timeout), cache size, conversation depth, LangSmith flags. All have sensible defaults.

### `src/db/` — Database layer
- `connection.py`: Creates SQLAlchemy engine with the `readonly_user`. Provides sync connection context managers. The agent never connects as `postgres` admin.
- `schema.sql`: Creates 5 tables (`customers`, `products`, `orders`, `order_items`, `reviews`) with FKs, ENUM type for order status, CHECK constraints, indexes, and `readonly_user` with SELECT-only grants. Mounted to `/docker-entrypoint-initdb.d/` for auto-execution on first Docker start.
- `seed.sql`: Inserts realistic e-commerce data across all 5 tables. Also auto-executed on first Postgres container start.

### `src/agent/` — Core agent

**State** (`state.py`): `AgentState` TypedDict carrying the full pipeline state:
- `messages` (conversation history), `query` (original NL), `generated_sql`, `validation_result`, `query_result`, `result_summary`, `error`, `error_class`, `retry_count`, `iteration_count`, `is_approved` (HITL flag).

**Graph** (`graph.py`): Wires all 5 nodes with conditional edges. Compiles with `MemorySaver` checkpointer and `interrupt_before=["execute"]` for HITL. Every invoke uses `thread_id` for session isolation.

**Nodes** (`nodes/`):
- `agent.py`: Constructs prompt from system message + history (truncated to 20) + schema context + few-shot examples. Calls `ChatOllama` with `.bind_tools()`. If tool call → sets `generated_sql`. If conversational → sets `result_summary`.
- `validate.py`: 5 checks — SQL starts with SELECT, no DDL/DML keywords, no injection patterns (`; DROP`, `UNION SELECT` from system tables), referenced tables exist, under 2000 chars. Sets `validation_result`.
- `execute.py`: Checks validation passed + HITL approved. Calls `execute_query()` tool. Wraps in try/except for error classification (syntax, permission, timeout, no_results). Applies row limit cap.
- `observe.py`: Pure formatting — markdown tables for small results, count summary for aggregates, graceful empty/error messages. Appends `AIMessage` to history.
- `reflect.py`: Routes: success → END, error + retries left → AGENT with error context message, retries exhausted → END with failure, max iterations → END with timeout message. Increments `retry_count` on retry.

**Tools** (`tools/sql_tools.py`): Two `@tool`-decorated LangChain tools:
- `get_schema_info()`: Uses SQLAlchemy `inspect()` for live schema (tables, columns, types, FKs) + merges `schema_desc.py` descriptions. Returns structured dict.
- `execute_query(sql)`: Runs raw SQL via `text()`. Rejects non-SELECT. Applies `LIMIT` cap if missing. Enforces timeout. Returns `list[dict]`.

**Prompts** (`prompts/`):
- `system.py`: System prompt defining the agent as an SQL-only assistant for the e-commerce DB.
- `sql_few_shot.py`: 5-8 NL→SQL pairs covering SELECT, JOIN, GROUP BY, ORDER BY + LIMIT, subquery. Critical for 3b model quality.
- `schema_desc.py`: `SCHEMA_DESCRIPTION` and `COLUMN_DESCRIPTIONS` dicts — human-written plain-English annotations that augment DDL for the LLM. Not optional.

**Error handlers** (`error_handlers.py`): 4 error classes only — `syntax`, `permission`, `timeout`, `no_results` (plus `unknown`). `classify_error()` maps SQLAlchemy exceptions. `should_retry()` respects max_retries=2. `build_retry_message()` creates LLM-friendly retry context per error type.

**Cache** (`cache.py`): `QueryCache` — in-memory LRU (max 128/session). Keyed by `(session_id, normalized_query)`. Only caches successful completions. Returns `cached: true` in metadata on hit.

**Tracing** (`tracing.py`): If `LANGCHAIN_TRACING_V2=true`, sets env vars. No-op otherwise. All LangGraph invocations automatically traced when enabled.

### `src/api/` — REST API

**App** (`app.py`): FastAPI instance with CORS (allow all for dev), lifespan handler (calls `setup_tracing()`), includes all route modules.

**Routes** (`routes/`):
- `health.py` (`GET /health`): Returns `{status, db: "connected"|"disconnected", ollama: "ready"|"unavailable"}`. Checks DB via SELECT 1, Ollama via GET `/api/tags`.
- `query.py` (`POST /query`): Accepts `{query, session_id?}`. Auto-generates UUID4 if no session_id. Checks cache → invoke graph → return `{status, sql, result_summary, result_data, session_id, metadata: {iterations, cached}}` or `{status: "pending_approval", proposed_sql, request_id}` for HITL. Errors return 200 with `{status: "error"}`.
- `approve.py` (`POST /query/approve`): Accepts `{request_id, session_id, approved}`. Updates graph state `is_approved`, resumes execution via `graph.invoke(None, config)`. Returns completed results or rejection.
- `stream.py` (`POST /query/stream`): Same input as `/query`. Uses `graph.astream_events()` for SSE — emits `event: agent|validate|execute|observe|complete` with node-specific data.
- `schema.py` (`GET /schema`): Returns all 5 tables with columns, types, and schema descriptions.
- `history.py` (`GET /history/{session_id}`): Reads `graph.get_state(config)` from checkpointer. Returns message array with roles and content.

### `scripts/` — Infrastructure

- `model_spike.py`: Standalone script — sends 5 NL→SQL queries to Ollama, rates accuracy, prints pass rate. Gate for model viability.
- `ollama-init.sh`: Starts `ollama serve`, then `ollama pull llama3.2:3b`. Runs on first Docker start.
- `app-entrypoint.sh`: Polls `http://ollama:11434/api/tags` every 5s for 60s. If Ollama ready → `exec uvicorn src.main:app`. Prevents app crashing when Ollama is still downloading the model.

### Docker (`docker-compose.yml`)

3 services:
- **app**: Built from `Dockerfile` (multi-stage, non-root user). Depends on postgres + ollama (healthcheck condition). Runs `scripts/app-entrypoint.sh`.
- **postgres**: `postgres:16-alpine`. Mounts `schema.sql` + `seed.sql` to `/docker-entrypoint-initdb.d/`. Healthcheck: `pg_isready`.
- **ollama**: `ollama/ollama:latest`. Persistent volume for model storage. Runs `scripts/ollama-init.sh`.

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