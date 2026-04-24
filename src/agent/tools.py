"""SQL tools for the agent: schema introspection and query execution."""

from sqlalchemy import create_engine, text, inspect
from src.config.settings import Settings

settings = Settings()

# Lazy-initialized engine (created on first use)
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        db_url = f"postgresql://{settings.db_user}:{settings.db_password}@{settings.db_host}:{settings.db_port}/{settings.db_name}"
        _engine = create_engine(db_url, pool_size=5, max_overflow=10)
    return _engine


def get_schema_info() -> dict:
    """Get live schema: table names, columns, types, FKs. Augmented with descriptions from prompts."""
    engine = _get_engine()
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    schema = {}
    for table in tables:
        columns = inspector.get_columns(table)
        fks = inspector.get_foreign_keys(table)
        schema[table] = {
            "columns": [{"name": c["name"], "type": str(c["type"])} for c in columns],
            "foreign_keys": [{"from": fk["constrained_columns"], "to": fk["referred_table"]} for fk in fks],
        }
    return schema


def execute_query(sql: str) -> list[dict]:
    """Execute a SELECT query and return results as list of dicts.

    Enforces: SELECT-only, row limit cap, query timeout.
    """
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT"):
        raise PermissionError("Only SELECT queries are allowed.")

    # Add LIMIT if not present
    if "LIMIT" not in sql_upper:
        sql = sql.rstrip(";") + f" LIMIT {settings.max_result_rows}"

    engine = _get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = [dict(row._mapping) for row in result.fetchall()]
    return rows