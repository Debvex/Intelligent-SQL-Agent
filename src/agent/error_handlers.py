from sqlalchemy.exc import OperationalError, ProgrammingError, IntegrityError, TimeoutError


ERROR_CLASSES = {"syntax", "permission", "timeout", "no_results", "unknown"}


def classify_error(exc: Exception) -> str:
    if isinstance(exc, ProgrammingError):
        return "syntax"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, OperationalError):
        msg = str(exc).lower()
        if "timeout" in msg or "deadlock" in msg:
            return "timeout"
        return "unknown"
    if isinstance(exc, IntegrityError):
        return "permission"
    if isinstance(exc, PermissionError):
        return "permission"
    msg = str(exc).lower()
    if "no result" in msg or "empty" in msg:
        return "no_results"
    return "unknown"


def should_retry(error_class: str, retry_count: int, max_retries: int) -> bool:
    if retry_count >= max_retries:
        return False
    return error_class in {"syntax", "timeout", "no_results"}


def build_retry_message(error_class: str, original_query: str, error_message: str) -> str:
    guidance = {
        "syntax": "This is a SQL syntax error. Verify table and column names match the schema, check JOIN conditions, and use correct PostgreSQL syntax.",
        "timeout": "The query timed out. Simplify it by adding LIMIT, reducing JOINs, or narrowing WHERE conditions.",
        "no_results": "No rows returned. Broaden the query, check case sensitivity in filters, or verify the data exists.",
        "permission": "Permission error. Ensure the query is SELECT-only and does not attempt to modify data.",
        "unknown": "An unexpected error occurred. Review the query carefully and try a different formulation.",
    }
    return (
        f"The previous query failed. Please regenerate the SQL.\n\n"
        f"User question: {original_query}\n"
        f"Error: {error_message}\n\n"
        f"Guidance: {guidance.get(error_class, guidance['unknown'])}"
    )
