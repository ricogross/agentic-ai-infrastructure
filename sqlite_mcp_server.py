import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DB_PATH = Path(__file__).parent / "demo.db"

mcp = FastMCP(
    name="sqlite-explorer",
    instructions="You have access to a local SQLite database. Use the tools to explore its schema and query data.",
)


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@mcp.tool()
def list_tables() -> str:
    """Return a list of all tables in the SQLite database."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        tables = [row["name"] for row in rows]
        return "\n".join(tables) if tables else "(no tables found)"
    except Exception as e:
        return f"SQL Error: {e}"
    finally:
        conn.close()


@mcp.tool()
def describe_table(table_name: str) -> str:
    """Return column names and types for the given table.

    Args:
        table_name: Name of the table to describe.
    """
    conn = _get_connection()
    try:
        rows = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        if not rows:
            return f"Table '{table_name}' not found or has no columns."
        lines = [f"{'Column':<20} {'Type':<15} {'Nullable':<10} {'PK':<5}"]
        lines.append("-" * 50)
        for r in rows:
            nullable = "YES" if not r["notnull"] else "NO"
            pk = "YES" if r["pk"] else ""
            lines.append(f"{r['name']:<20} {r['type']:<15} {nullable:<10} {pk:<5}")
        return "\n".join(lines)
    except Exception as e:
        return f"SQL Error: {e}"
    finally:
        conn.close()


@mcp.tool()
def query(sql: str) -> str:
    """Execute a read-only SQL query against the database and return results.

    Only SELECT statements are allowed.

    Args:
        sql: The SQL SELECT statement to execute.
    """
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        return "Error: only SELECT queries are allowed."

    conn = _get_connection()
    try:
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        if not rows:
            return "(no results)"

        # Format as a simple text table
        columns = [desc[0] for desc in cursor.description]
        col_widths = [len(c) for c in columns]
        str_rows = []
        for row in rows:
            vals = [str(v) for v in row]
            for i, v in enumerate(vals):
                col_widths[i] = max(col_widths[i], len(v))
            str_rows.append(vals)

        header = "  ".join(c.ljust(w) for c, w in zip(columns, col_widths))
        sep = "  ".join("-" * w for w in col_widths)
        body = "\n".join(
            "  ".join(v.ljust(w) for v, w in zip(vals, col_widths)) for vals in str_rows
        )
        return f"{header}\n{sep}\n{body}"
    except Exception as e:
        return f"SQL Error: {e}"
    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
