"""
LangGraph StateGraph — state, nodes, routing, and compilation in ONE file.

Read top-to-bottom:
1. State definition (whiteboard carrying data between nodes)
2. Node functions (agent, validate, execute, observe, reflect)
3. Conditional routing functions
4. Graph wiring and compilation
"""

from typing import TypedDict
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, AIMessage

from src.config.settings import Settings
from src.agent.tools import get_schema_info, execute_query
from src.agent.prompts import SYSTEM_PROMPT, FEW_SHOT_EXAMPLES
from src.agent.error_handlers import classify_error, should_retry, build_retry_message

settings = Settings()


# ============================================================
# 1. STATE
# ============================================================

class AgentState(TypedDict):
    messages: list              # Conversation history (BaseMessage)
    query: str                  # Original NL query
    generated_sql: str | None   # SQL produced by agent
    validation_result: dict | None  # {"is_valid": bool, "errors": [str]}
    query_result: list | None   # Rows from DB
    result_summary: str | None  # Human-readable result
    error: str | None           # Error message
    error_class: str | None     # "syntax" | "permission" | "timeout" | "no_results" | "unknown"
    retry_count: int            # Retry attempts (max 2)
    iteration_count: int       # Graph iterations (max 10)
    is_approved: bool | None    # HITL: None=pending, True=approved, False=rejected


# ============================================================
# 2. NODES
# ============================================================

def agent_node(state: AgentState) -> dict:
    """AGENT — LLM decides: generate SQL or respond conversationally."""
    history = state["messages"][-settings.conversation_history_depth:]
    schema_ctx = get_schema_info()
    few_shot_ctx = "\n\n".join(
        f"Q: {ex['question']}\nSQL: {ex['sql']}" for ex in FEW_SHOT_EXAMPLES
    )
    prompt = f"{SYSTEM_PROMPT}\n\nSchema:\n{schema_ctx}\n\nFew-shot examples:\n{few_shot_ctx}\n\nUser question: {state['query']}"
    messages = history + [HumanMessage(content=prompt)]

    llm = ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url)
    # TODO: bind SQL tools with .bind_tools(), parse tool calls vs conversational response
    response = llm.invoke(messages)

    return {
        "messages": messages + [response],
        "iteration_count": state.get("iteration_count", 0) + 1,
        "generated_sql": None,      # TODO: extract from tool call
        "result_summary": None,      # TODO: extract from conversational response
    }


def validate_node(state: AgentState) -> dict:
    """VALIDATE — 5 safety checks on generated SQL."""
    sql = state.get("generated_sql") or ""
    errors = []
    known_tables = {"customers", "products", "orders", "order_items", "reviews"}

    if not sql.strip().upper().startswith("SELECT"):
        errors.append("Only SELECT queries allowed (no DDL/DML).")
    for pattern in ["; DROP", "UNION SELECT", "PG_", "INFORMATION_SCHEMA"]:
        if pattern in sql.upper():
            errors.append(f"Blocked pattern: {pattern}")
    if not sql.strip():
        errors.append("No SQL generated.")
    # TODO: extract table names from SQL and validate against known_tables
    if len(sql) > 2000:
        errors.append("SQL too long (over 2000 chars).")

    return {"validation_result": {"is_valid": len(errors) == 0, "errors": errors}}


def execute_node(state: AgentState) -> dict:
    """EXECUTE — run validated SQL, handle errors."""
    validation = state.get("validation_result", {})
    if not validation.get("is_valid"):
        return {"query_result": None, "error": "Validation failed: " + "; ".join(validation.get("errors", []))}
    if state.get("is_approved") is False:
        return {"query_result": None, "error": "Query rejected by user."}

    try:
        result = execute_query(state.get("generated_sql", ""))
        if not result:
            return {"query_result": [], "error_class": "no_results"}
        return {"query_result": result}
    except Exception as e:
        return {"error": str(e), "error_class": classify_error(e)}


def observe_node(state: AgentState) -> dict:
    """OBSERVE — format results as markdown table or summary."""
    result = state.get("query_result")
    error = state.get("error")

    if error:
        summary = f"Error: {error}"
    elif not result:
        summary = "No results found."
    elif len(result) <= 10:
        headers = list(result[0].keys())
        rows = [" | ".join(str(row.get(h, "")) for h in headers) for row in result]
        summary = f"| {' | '.join(headers)} |\n| {' | '.join('---' for _ in headers)} |\n"
        summary += "\n".join(f"| {r} |" for r in rows)
    else:
        summary = f"Found {len(result)} results. Showing first 10."

    return {"result_summary": summary, "messages": state.get("messages", []) + [AIMessage(content=summary)]}


def reflect_node(state: AgentState) -> dict:
    """REFLECT — decide: done, retry, or fail."""
    if state.get("result_summary") and not state.get("error"):
        return {}  # Success → END

    if state.get("error") and should_retry(
        state.get("error_class", "unknown"), state.get("retry_count", 0), settings.max_retries
    ):
        retry_msg = build_retry_message(
            state.get("error_class", "unknown"), state.get("query", ""), state.get("error", "")
        )
        return {
            "retry_count": state.get("retry_count", 0) + 1,
            "messages": state.get("messages", []) + [HumanMessage(content=retry_msg)],
        }

    return {}  # Retries exhausted → END


# ============================================================
# 3. ROUTING
# ============================================================

def route_after_agent(state: AgentState) -> str:
    return "validate" if state.get("generated_sql") else END


def route_after_validate(state: AgentState) -> str:
    v = state.get("validation_result", {})
    return "execute" if v.get("is_valid") else "agent"


def route_after_reflect(state: AgentState) -> str:
    if state.get("result_summary") and not state.get("error"):
        return END
    if state.get("retry_count", 0) >= settings.max_retries:
        return END
    if state.get("iteration_count", 0) >= settings.max_iterations:
        return END
    return "agent" if state.get("error") else END


# ============================================================
# 4. GRAPH WIRING
# ============================================================

builder = StateGraph(AgentState)
builder.add_node("agent", agent_node)
builder.add_node("validate", validate_node)
builder.add_node("execute", execute_node)
builder.add_node("observe", observe_node)
builder.add_node("reflect", reflect_node)

builder.set_entry_point("agent")
builder.add_conditional_edges("agent", route_after_agent)
builder.add_conditional_edges("validate", route_after_validate)
builder.add_edge("execute", "observe")
builder.add_edge("observe", "reflect")
builder.add_conditional_edges("reflect", route_after_reflect)

graph = builder.compile(
    checkpointer=MemorySaver(),
    interrupt_before=["execute"],
)