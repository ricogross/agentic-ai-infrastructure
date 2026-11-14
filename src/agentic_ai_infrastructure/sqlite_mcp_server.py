import sqlite3

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from agentic_ai_infrastructure import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "demo.db"

# The actions a statement in `query` may perform. SQLite's authorizer checks every action of a
# statement, so this also stops ATTACH and VACUUM INTO, which write files even on a read-only
# connection.
READ_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}

mcp = FastMCP(
    name="sqlite-explorer",
    instructions="You have access to a local SQLite database. Use the tools to explore its schema and query data.",
)


def _get_connection() -> sqlite3.Connection:
    # mode=ro: SQLite refuses every write, and a missing file is an error instead of a new,
    # empty database.
    try:
        conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    except sqlite3.OperationalError as e:
        raise ToolError(f"cannot open {DB_PATH.name} ({e}), run `uv run seed-db` first") from e
    conn.row_factory = sqlite3.Row
    return conn


def _allow_only_reads(action: int, *_: str | None) -> int:
    return sqlite3.SQLITE_OK if action in READ_ACTIONS else sqlite3.SQLITE_DENY


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
    except sqlite3.Error as e:
        raise ToolError(f"SQL error: {e}") from e
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
            raise ToolError(f"table {table_name!r} not found or has no columns")
        lines = [f"{'Column':<20} {'Type':<15} {'Nullable':<10} {'PK':<5}"]
        lines.append("-" * 50)
        for r in rows:
            nullable = "YES" if not r["notnull"] else "NO"
            pk = "YES" if r["pk"] else ""
            lines.append(f"{r['name']:<20} {r['type']:<15} {nullable:<10} {pk:<5}")
        return "\n".join(lines)
    except sqlite3.Error as e:
        raise ToolError(f"SQL error: {e}") from e
    finally:
        conn.close()


@mcp.tool()
def query(sql: str) -> str:
    """Execute a read-only SQL query against the database and return results.

    Only statements that read data are allowed, e.g. SELECT or WITH ... SELECT.

    Args:
        sql: The SQL query to execute.
    """
    conn = _get_connection()
    conn.set_authorizer(_allow_only_reads)
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
    except sqlite3.Error as e:
        if e.sqlite_errorname == "SQLITE_AUTH":
            raise ToolError("only read-only queries are allowed (SELECT, WITH ... SELECT)") from e
        raise ToolError(f"SQL error: {e}") from e
    finally:
        conn.close()


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
