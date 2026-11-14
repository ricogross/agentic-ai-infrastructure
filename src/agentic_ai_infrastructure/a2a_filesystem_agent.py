import functools

import langchain_mcp_adapters.sessions
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
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from starlette.applications import Starlette

from agentic_ai_infrastructure import PROJECT_ROOT

load_dotenv()

SANDBOX_DIR = str(PROJECT_ROOT / "sandbox")
# Pinned: without a version, `npx -y` runs whatever npm published last, on every start.
FILESYSTEM_SERVER = "@modelcontextprotocol/server-filesystem@2.3.0"

# Workaround: the MCP client starts the server without a console (CREATE_NO_WINDOW on
# Windows) but hands it this process's stderr. If that stderr is a real console, the
# Node-based filesystem server dies on its first log write ("McpError: Connection
# closed"). langchain-mcp-adapters has no option for the server's stderr, so send it
# to a log file instead.
SERVER_LOG = open(PROJECT_ROOT / "filesystem_mcp_server.log", "a", encoding="utf-8")  # noqa: SIM115
# partial() makes errlog keyword-only; the adapter only ever passes the server parameters.
langchain_mcp_adapters.sessions.stdio_client = functools.partial(  # ty: ignore[invalid-assignment]
    langchain_mcp_adapters.sessions.stdio_client, errlog=SERVER_LOG
)

MODEL = "openai:gpt-4o-mini"
PORT = 5002

SYSTEM_PROMPT = f"""\
You are a filesystem assistant specialized in browsing and reading files \
within a sandboxed directory.

The allowed root directory is: {SANDBOX_DIR}

Your workflow:
1. If you need to find files, start with directory_tree or list_directory.
2. Use read_text_file to read file contents.
3. Use get_file_info for metadata (size, timestamps).
4. Present findings clearly.

You can ONLY access files inside the sandbox directory.
"""


class FilesystemAgentExecutor(AgentExecutor):
    """Bridges A2A requests to the LangChain filesystem agent with streaming."""

    def __init__(self):
        self._agent = None
        self._client = None

    async def _get_agent(self):
        if self._agent is None:
            self._client = MultiServerMCPClient(
                {
                    "filesystem": {
                        "command": "npx",
                        "args": [
                            "-y",
                            FILESYSTEM_SERVER,
                            SANDBOX_DIR,
                        ],
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
        if context.message is None:
            raise ValueError("A2A request without a message")
        agent = await self._get_agent()
        # A2A 1.0: the event stream of a task has to start with the task itself.
        task = context.current_task
        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()

        user_text = context.get_user_input()
        print(f"[A2A] Received request: {user_text!r}", flush=True)
        accumulated = ""

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

            if isinstance(chunk, AIMessage) and isinstance(chunk.content, str) and chunk.content:
                accumulated += chunk.content
                msg = updater.new_agent_message([Part(text=accumulated)])
                await updater.update_status(TaskState.TASK_STATE_WORKING, message=msg)

        print(f"[A2A] Streaming response complete ({len(accumulated)} chars)", flush=True)
        final_msg = updater.new_agent_message([Part(text=accumulated)])
        await updater.complete(message=final_msg)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # The SDK stops the running execute() itself, so only the new state is left to report.
        if context.task_id is None or context.context_id is None:
            raise ValueError("A2A cancel request without task or context ID")
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()


skill = AgentSkill(
    id="filesystem_browse",
    name="Filesystem Browser",
    description="Browse directories, read text files, get file metadata, and search "
    "for files within a sandboxed directory tree.",
    tags=["filesystem", "files", "directory", "read", "browse"],
    examples=[
        "What files are in the sandbox?",
        "Read the meeting notes",
        "Show me the directory tree",
        "What does the config.json file contain?",
    ],
)

agent_card = AgentCard(
    name="Filesystem Agent",
    description="A specialized agent for browsing and reading files in a sandboxed "
    "directory containing notes and configuration files.",
    supported_interfaces=[
        AgentInterface(
            protocol_binding="JSONRPC",
            protocol_version="1.0",
            url=f"http://localhost:{PORT}/",
        ),
    ],
    version="1.0.0",
    default_input_modes=["text"],
    default_output_modes=["text"],
    capabilities=AgentCapabilities(streaming=True),
    skills=[skill],
)


def main():
    handler = DefaultRequestHandler(
        agent_executor=FilesystemAgentExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=agent_card,
    )
    app = Starlette(
        routes=create_agent_card_routes(agent_card) + create_jsonrpc_routes(handler, rpc_url="/")
    )
    print(f"Filesystem Agent (A2A) starting on http://localhost:{PORT}")
    print(f"Agent Card: http://localhost:{PORT}/.well-known/agent-card.json")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
