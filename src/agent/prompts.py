"""Prompts for the SQL agent: system prompt, few-shot examples, and schema descriptions."""

# ============================================================
# SYSTEM PROMPT — defines the agent's role and rules
# ============================================================

SYSTEM_PROMPT = """You are an intelligent SQL assistant for an e-commerce database.
Your job is to translate natural language questions into SQL queries.

Rules:
- Generate ONLY SELECT queries. Never produce INSERT, UPDATE, DELETE, DROP, ALTER, or CREATE.
- Always use proper table and column names from the provided schema.
- Add LIMIT clauses when appropriate to avoid large result sets.
- If you cannot answer a question with SQL, respond conversationally explaining why.
- Do not make up tables or columns that don't exist in the schema.
"""


# ============================================================
# FEW-SHOT EXAMPLES — teaches the model NL→SQL patterns
# ============================================================

FEW_SHOT_EXAMPLES = [
    {
        "question": "How many customers do we have?",
        "sql": "SELECT COUNT(*) AS total_customers FROM customers;",
    },
    {
        "question": "Show me all products in the Electronics category",
        "sql": "SELECT name, price, stock_quantity FROM products WHERE category = 'Electronics' ORDER BY price;",
    },
    {
        "question": "What is the total revenue from all orders?",
        "sql": "SELECT SUM(total_amount) AS total_revenue FROM orders;",
    },
    {
        "question": "List the top 5 customers by total spending",
        "sql": """SELECT c.first_name, c.last_name, SUM(o.total_amount) AS total_spent
FROM customers c
JOIN orders o ON c.id = o.customer_id
GROUP BY c.id, c.first_name, c.last_name
ORDER BY total_spent DESC
LIMIT 5;""",
    },
    {
        "question": "How many orders were placed in January 2024?",
        "sql": """SELECT COUNT(*) AS order_count
FROM orders
WHERE order_date >= '2024-01-01' AND order_date < '2024-02-01';""",
    },
    {
        "question": "Which products have never been ordered?",
        "sql": """SELECT p.name, p.price
FROM products p
LEFT JOIN order_items oi ON p.id = oi.product_id
WHERE oi.id IS NULL;""",
    },
    {
        "question": "What is the average rating for each product category?",
        "sql": """SELECT p.category, AVG(r.rating) AS avg_rating, COUNT(r.id) AS review_count
FROM products p
JOIN reviews r ON p.id = r.product_id
GROUP BY p.category
ORDER BY avg_rating DESC;""",
    },
]


# ============================================================
# SCHEMA DESCRIPTIONS — plain-English annotations for the LLM
# These are NOT optional. The LLM needs semantic context beyond DDL.
# ============================================================

SCHEMA_DESCRIPTION = {
    "customers": "Stores customer information. Each customer has a unique email. Used in JOINs with orders and reviews.",
    "products": "Product catalog with pricing and inventory. Category is one of: Electronics, Clothing, Home, Books, Sports. stock_quantity shows current availability.",
    "orders": "Customer purchase records. Status ENUM: pending, processing, shipped, delivered, cancelled. total_amount is pre-calculated order total.",
    "order_items": "Line items within each order. Links orders to products with quantity and unit_price at time of purchase (may differ from current product.price).",
    "reviews": "Product reviews by customers. Rating is 1-5 integer. Comment is optional text. review_date is when the review was submitted.",
}

COLUMN_DESCRIPTIONS = {
    "customers.email": "Unique email address, used for identification.",
    "customers.phone": "Optional phone number.",
    "orders.status": "One of: pending, processing, shipped, delivered, cancelled. Not a free-text field.",
    "orders.total_amount": "Pre-calculated order total in USD (decimal). Sum of order_items.unit_price * quantity for that order.",
    "products.price": "Price per unit in USD (decimal).",
    "products.stock_quantity": "Current number of units available in inventory.",
    "products.category": "One of: Electronics, Clothing, Home, Books, Sports.",
    "order_items.unit_price": "Price per unit at time of order (frozen, may differ from current product.price).",
    "order_items.quantity": "Number of units of this product in the order.",
    "reviews.rating": "Integer 1-5, where 1 is worst and 5 is best.",
}