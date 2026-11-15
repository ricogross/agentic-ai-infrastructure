"""A2A server around a LangChain agent that works with the tools of MCP servers.

Specialized agents are built from this module. They only differ in their MCP servers,
their system prompt and what their Agent Card advertises.
"""

import contextlib
from collections.abc import AsyncGenerator

import uvicorn
from a2a.helpers import new_task_from_user_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Part,
    TaskState,
)
from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from starlette.applications import Starlette

from agentic_ai_infrastructure import PROJECT_ROOT

MODEL = "openai:gpt-4o-mini"


class McpAgentExecutor(AgentExecutor):
    """Bridges A2A requests to a LangChain agent with MCP tools, with streaming."""

    def __init__(
        self,
        mcp_servers: dict[str, StdioServerParameters],
        system_prompt: str,
        model: str | BaseChatModel = MODEL,
    ):
        self._mcp_servers = mcp_servers
        self._system_prompt = system_prompt
        self._model = model
        self._agent = None

    @contextlib.asynccontextmanager
    async def connected(self) -> AsyncGenerator[None]:
        """Start the MCP servers, keep one session to each open and build the agent."""
        async with contextlib.AsyncExitStack() as stack:
            tools: list[BaseTool] = []
            for name, server in self._mcp_servers.items():
                # The server's stderr goes to a log file, not to this process's stderr: on
                # Windows the server runs without a console (CREATE_NO_WINDOW), and a Node-based
                # server dies when it writes to the console of this process ("McpError:
                # Connection closed"). The file is opened once while the app starts, before
                # any request (so the blocking open() is harmless), and closed by the stack.
                log_path = PROJECT_ROOT / f"{name}_mcp_server.log"
                errlog = stack.enter_context(open(log_path, "a", encoding="utf-8"))  # noqa: ASYNC230, SIM115
                read, write = await stack.enter_async_context(stdio_client(server, errlog=errlog))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                tools += await load_mcp_tools(session)
            for tool in tools:
                tool.handle_tool_error = True
            self._agent = create_agent(self._model, tools, system_prompt=self._system_prompt)
            try:
                yield
            finally:
                self._agent = None

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.message is None:
            raise ValueError("A2A request without a message")
        if self._agent is None:
            raise RuntimeError("MCP servers not connected, see McpAgentExecutor.connected()")
        agent = self._agent
        # A2A 1.0: the event stream of a task has to start with the task itself.
        task = context.current_task
        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
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
                msg = updater.new_agent_message([Part(text=accumulated)])
                await updater.update_status(TaskState.TASK_STATE_WORKING, message=msg)

        print(f"[A2A] Streaming response complete ({len(accumulated)} chars)", flush=True)
        final_msg = updater.new_agent_message([Part(text=accumulated)])
        await updater.complete(message=final_msg)  # signals completion to A2A caller

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # The SDK stops the running execute() itself, so only the new state is left to report.
        if context.task_id is None or context.context_id is None:
            raise ValueError("A2A cancel request without task or context ID")
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()


def build_agent_card(name: str, description: str, skill: AgentSkill, port: int) -> AgentCard:
    """Agent Card for an agent served by `serve()` on localhost at `port`."""
    return AgentCard(
        name=name,
        description=description,
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                protocol_version="1.0",
                url=f"http://localhost:{port}/",
            ),
        ],
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )


def serve(agent_card: AgentCard, executor: McpAgentExecutor, port: int) -> None:
    """Serve the Agent Card and the A2A JSON-RPC endpoint on localhost at `port`."""
    handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )
    app = Starlette(
        routes=create_agent_card_routes(agent_card) + create_jsonrpc_routes(handler, rpc_url="/"),
        # The MCP servers live as long as the app: they start before the first request is
        # accepted and stop when uvicorn shuts down.
        lifespan=lambda _app: executor.connected(),
    )
    print(f"{agent_card.name} (A2A) starting on http://localhost:{port}")
    print(f"Agent Card: http://localhost:{port}/.well-known/agent-card.json")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
