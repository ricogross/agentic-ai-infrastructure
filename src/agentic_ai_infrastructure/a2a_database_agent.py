import sys

import uvicorn
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils.errors import ServerError
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

MODEL = "openai:gpt-4o-mini"
PORT = 5001

SYSTEM_PROMPT = """\
You are a database assistant specialized in exploring and querying a SQLite \
database. Use the connected MCP server to interact with the database.

Your workflow:
1. If you don't know the schema yet, start by listing tables and describing them.
2. Write precise SQL queries to answer the user's question.
3. Present results clearly and concisely.

Only SELECT statements are allowed.
"""


class DatabaseAgentExecutor(AgentExecutor):
    """Bridges A2A requests to the LangChain database agent with streaming."""

    def __init__(self):
        self._agent = None
        self._client = None

    async def _get_agent(self):
        if self._agent is None:
            self._client = MultiServerMCPClient(
                {
                    "sqlite": {
                        "command": sys.executable,
                        "args": ["-m", "agentic_ai_infrastructure.sqlite_mcp_server"],
                        "transport": "stdio",
                    },
                }
            )
            tools = await self._client.get_tools()
            for tool in tools:
                tool.handle_tool_error = True
            self._agent = create_agent(MODEL, tools, system_prompt=SYSTEM_PROMPT)
        return self._agent

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.task_id is None or context.context_id is None:
            raise ValueError("A2A request without task or context ID")
        agent = await self._get_agent()
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.start_work()

        user_text = context.get_user_input()  # extract text from incoming A2A message
        print(f"[A2A] Received request: {user_text!r}", flush=True)
        accumulated = ""

        # LangChain ReAct loop
        async for chunk, _metadata in agent.astream(
            {"messages": [{"role": "user", "content": user_text}]},
            stream_mode="messages",
        ):
            # Log MCP tool calls and results
            if isinstance(chunk, AIMessage) and chunk.tool_calls:
                for tc in chunk.tool_calls:
                    print(
                        f"[MCP] tool call: {tc['name']}({tc.get('args', {})})",
                        flush=True,
                    )
            if isinstance(chunk, ToolMessage):
                preview = str(chunk.content)[:120]
                print(f"[MCP] tool result: {preview}", flush=True)

            # Stream the agent's own text (not tool results) back to the caller over A2A
            if isinstance(chunk, AIMessage) and isinstance(chunk.content, str) and chunk.content:
                accumulated += chunk.content
                msg = updater.new_agent_message([Part(root=TextPart(text=accumulated))])
                await updater.update_status(TaskState.working, message=msg)

        print(f"[A2A] Streaming response complete ({len(accumulated)} chars)", flush=True)
        final_msg = updater.new_agent_message([Part(root=TextPart(text=accumulated))])
        await updater.complete(message=final_msg)  # signals completion to A2A caller

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # A running LangChain agent can't be stopped, so report that as defined by A2A.
        raise ServerError(error=UnsupportedOperationError())


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

agent_card = AgentCard(
    name="Database Agent",
    description="A specialized agent for exploring and querying a SQLite database "
    "with products and orders data.",
    url=f"http://localhost:{PORT}/",
    version="1.0.0",
    default_input_modes=["text"],
    default_output_modes=["text"],
    capabilities=AgentCapabilities(streaming=True),
    skills=[skill],
)


def main():
    handler = DefaultRequestHandler(
        agent_executor=DatabaseAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )
    app = A2AStarletteApplication(agent_card=agent_card, http_handler=handler)
    print(f"Database Agent (A2A) starting on http://localhost:{PORT}")
    print(f"Agent Card: http://localhost:{PORT}/.well-known/agent-card.json")
    uvicorn.run(app.build(), host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
