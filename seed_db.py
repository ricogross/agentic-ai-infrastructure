"""
Seed script — creates a local SQLite database named 'demo.db' with sample data.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "demo.db"


def main():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS orders")
    cur.execute("DROP TABLE IF EXISTS products")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            category    TEXT    NOT NULL,
            price       REAL    NOT NULL,
            in_stock    INTEGER NOT NULL DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id  INTEGER NOT NULL REFERENCES products(id),
            customer    TEXT    NOT NULL,
            quantity    INTEGER NOT NULL,
            order_date  TEXT    NOT NULL
        )
    """)

    products = [
        ("Mechanical Keyboard", "Electronics", 89.99, 1),
        ("USB-C Hub", "Electronics", 34.50, 1),
        ("Standing Desk", "Furniture", 349.00, 1),
        ("Monitor Arm", "Furniture", 79.95, 0),
        ("Webcam HD", "Electronics", 59.99, 1),
        ("Desk Lamp", "Furniture", 42.00, 1),
        ("Wireless Mouse", "Electronics", 29.99, 1),
        ("Noise-Cancel Headset", "Electronics", 149.00, 0),
    ]
    cur.executemany(
        "INSERT INTO products (name, category, price, in_stock) VALUES (?, ?, ?, ?)",
        products,
    )

    orders = [
        (1, "Alice", 2, "2025-01-15"),
        (3, "Bob", 1, "2025-02-03"),
        (5, "Charlie", 1, "2025-02-10"),
        (2, "Alice", 3, "2025-02-14"),
        (7, "Diana", 1, "2025-02-20"),
        (1, "Eve", 1, "2025-02-25"),
        (6, "Bob", 2, "2025-03-01"),
    ]
    cur.executemany(
        "INSERT INTO orders (product_id, customer, quantity, order_date) VALUES (?, ?, ?, ?)",
        orders,
    )

    conn.commit()
    conn.close()
    print(f"Database created at {DB_PATH}")
    print(f"  - {len(products)} products inserted")
    print(f"  - {len(orders)} orders inserted")


if __name__ == "__main__":
    main()
