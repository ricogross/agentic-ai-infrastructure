import sys

from a2a.types import AgentSkill
from mcp import StdioServerParameters

from agentic_ai_infrastructure import config
from agentic_ai_infrastructure.a2a_mcp_agent import McpAgentExecutor, build_agent_card, serve

PORT = config.DATABASE_AGENT_PORT

SYSTEM_PROMPT = """\
You are a database assistant specialized in exploring and querying a SQLite \
database. Use the connected MCP server to interact with the database.

Your workflow:
1. If you don't know the schema yet, start by listing tables and describing them.
2. Write precise SQL queries to answer the user's question.
3. Present results clearly and concisely.

Only SELECT statements are allowed.
"""

MCP_SERVERS = {
    "sqlite": StdioServerParameters(
        command=sys.executable,
        args=["-m", "agentic_ai_infrastructure.sqlite_mcp_server"],
    ),
}

skill = AgentSkill(
    id="database_query",
    name="Database Query",
    description="Explore SQLite database schemas and execute read-only SQL queries. "
    "Can list tables, describe columns, and run SELECT statements.",
    tags=["database", "sql", "sqlite", "query", "schema"],
    examples=[
        "What tables are in the database?",
        "Which product has the most orders?",
        "Show me all products under $50",
        "How many orders did Alice place?",
    ],
)

agent_card = build_agent_card(
    name="Database Agent",
    description="A specialized agent for exploring and querying a SQLite database "
    "with products and orders data.",
    skill=skill,
    port=PORT,
)


def main():
    serve(agent_card, McpAgentExecutor(MCP_SERVERS, SYSTEM_PROMPT), PORT)


if __name__ == "__main__":
    main()
