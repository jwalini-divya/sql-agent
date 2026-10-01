"""A small sample shop database (SQLite, built into Python) and a safe way to query it."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "shop.db"

SAMPLE_DATA = """
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, city TEXT);
CREATE TABLE products  (id INTEGER PRIMARY KEY, name TEXT, category TEXT, price REAL);
CREATE TABLE orders    (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id),
                        product_id INTEGER REFERENCES products(id), quantity INTEGER, order_date TEXT);

INSERT INTO customers VALUES (1, 'Asha', 'Hyderabad'), (2, 'Ravi', 'Chennai'), (3, 'Meena', 'Bengaluru'),
                             (4, 'Kiran', 'Hyderabad'), (5, 'Sara', 'Mumbai');
INSERT INTO products VALUES (1, 'Laptop', 'Electronics', 55000), (2, 'Headphones', 'Electronics', 2500),
                            (3, 'Office Chair', 'Furniture', 7000), (4, 'Desk Lamp', 'Furniture', 1200),
                            (5, 'Notebook', 'Stationery', 60);
INSERT INTO orders VALUES (1, 1, 1, 1, '2026-07-03'), (2, 1, 2, 2, '2026-07-10'), (3, 2, 3, 1, '2026-07-15'),
                          (4, 3, 5, 20, '2026-08-01'), (5, 4, 1, 1, '2026-08-05'), (6, 4, 4, 2, '2026-08-20'),
                          (7, 5, 2, 1, '2026-09-02'), (8, 2, 5, 10, '2026-09-12'), (9, 3, 3, 2, '2026-09-18'),
                          (10, 5, 1, 1, '2026-09-25');
"""


def create_sample_db(path: Path = DB_PATH) -> None:
    """Create the sample database the first time (does nothing if it already exists)."""
    if not path.exists():
        with sqlite3.connect(path) as conn:
            conn.executescript(SAMPLE_DATA)


def get_schema(path: Path = DB_PATH) -> str:
    """The CREATE TABLE statements, so the LLM knows the tables and columns."""
    with sqlite3.connect(path) as conn:
        return "\n".join(row[0] for row in conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table'"))


def run_query(sql: str, path: Path = DB_PATH, max_rows: int = 50) -> list[dict]:
    """Run one SELECT query safely and return the rows.

    Three guardrails: only SELECT/WITH is accepted, the connection is read-only
    (so even a hidden write fails), and sqlite3 runs only one statement at a time.
    """
    if not sql.lstrip().lower().startswith(("select", "with")):
        raise ValueError("Only SELECT queries are allowed")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(sql).fetchmany(max_rows)]
    finally:
        conn.close()
