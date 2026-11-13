# Agentic AI PoC

A multi-agent system demonstrating three open agentic protocols working together:

- **MCP** (Model Context Protocol) — agents access tools via MCP servers
- **A2A** (Agent-to-Agent) — the orchestrator agent delegates tasks to specialized agents over HTTP
- **AG-UI** (Agent-User Interaction) — the orchestrator agent streams agent actions to a React frontend in real time

## Architecture

```
┌─────────────────────┐
│   React Frontend    │   CopilotKit (AG-UI)
│   (Next.js)         │◄──────────────────────┐
│   localhost:3000    │                       │
└─────────────────────┘                       │
                                              │
                                   ┌──────────┴───────────┐
                                   │  Orchestrator Agent  │
                                   │  localhost:8123      │
                                   │                      │
                                   │  LangGraph with      │
                                   │  A2A delegation tools│
                                   └──────┬─────┬─────────┘
                                          │     │
                              A2A (HTTP)  │     │  A2A (HTTP)
                                          │     │
                    ┌─────────────────────┘     └────────────────────┐
                    │                                                │
         ┌──────────▼───────────┐                     ┌──────────────▼──────────┐
         │  Database Agent      │                     │  Filesystem Agent       │
         │  localhost:5001      │                     │  localhost:5002         │
         │                      │                     │                         │
         │  LangChain + MCP     │                     │  LangChain + MCP        │
         └──────────┬───────────┘                     └──────────────┬──────────┘
                    │ MCP (stdio)                                    │ MCP (stdio)
         ┌──────────▼───────────┐                     ┌──────────────▼──────────┐
         │ sqlite_mcp_server.py │                     │  server-filesystem      │
         │    accesses local    │                     │     accesses local      │
         │    SQLite database   │                     │     directory           │
         │    → demo.db         │                     │     → sandbox/          │
         └──────────────────────┘                     └─────────────────────────┘
```

**Four processes** run simultaneously:

| Process | File | Port | Role |
|---------|------|------|------|
| Database Agent | `a2a_database_agent.py` | 5001 | Queries SQLite via a custom MCP server |
| Filesystem Agent | `a2a_filesystem_agent.py` | 5002 | Browses/reads files via the prebuilt Filesystem MCP server |
| Orchestrator | `orchestrator_agent.py` | 8123 | LangGraph agent — routes questions via A2A delegation tools |
| Frontend | `frontend/` (Next.js) | 3000 | CopilotKit React chat UI |

## How it works

1. **Orchestrator** — A LangGraph agent with two tools:
   `ask_database_agent` and `ask_filesystem_agent`. Each tool sends the
   question to the corresponding A2A agent and returns the response.

2. **LLM routing** — When the user sends a message, the LLM of the **Orchestrator** decides:
   - **Simple questions** → answer directly
   - **Database questions** → call `ask_database_agent` tool (A2A delegation)
   - **Filesystem questions** → call `ask_filesystem_agent` tool (A2A delegation)
   - **Cross-domain questions** → call both tools, synthesize results

3. **AG-UI streaming** — CopilotKit's `LangGraphAgent` adapter connects to
   the LangGraph server (`orchestrator_agent.py`) and translates its streaming events into AG-UI events
   for the React frontend. Tool calls, intermediate steps and streamed text
   are all visible in the chat UI automatically.

## Protocols

| Protocol | Transport | Where used |
|----------|-----------|------------|
| **AG-UI** | HTTP (via CopilotKit + LangGraph) | Frontend ↔ Orchestrator |
| **A2A** | HTTP, JSON-RPC 2.0 | Orchestrator → Specialized agents |
| **MCP** | stdio, JSON-RPC 2.0 | Specialized agent → Its MCP server |

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (installs Python 3.14 automatically)
- Node.js 20+
- pnpm (`npm install -g pnpm@9`)
- OpenAI API key

## Initial Setup

```bash
# 1. Set up the Python backend (creates .venv from uv.lock)
uv sync

# 2. Create a .env file in the project root containing your OpenAI API key:
OPENAI_API_KEY=sk-proj-...

# 3. Seed the sample database
uv run seed-db

# 4. Set up the frontend
cd frontend
pnpm install
```

## Running the Agentic AI system

Start each service in its own terminal in the following order:

```bash
# Terminal 1 — Database Agent
uv run database-agent

# Terminal 2 — Filesystem Agent
uv run filesystem-agent

# Terminal 3 — LangGraph Orchestrator
uv run langgraph dev --port 8123 --no-browser

# Terminal 4 — Frontend
cd frontend
pnpm dev
```

Then open http://localhost:3000 in your browser.
There the chat UI is hosted.

## Development

Ruff (lint and format) and ty (type checks) are dev dependencies and come with `uv sync`:

```bash
uv run ruff check     # lint
uv run ruff format    # format
uv run ty check       # type-check
```

## Files

| File | Purpose |
|------|---------|
| `src/agentic_ai_infrastructure/` | Python package with all backend code (`PROJECT_ROOT` in `__init__.py`) |
| `src/agentic_ai_infrastructure/orchestrator_agent.py` | LangGraph orchestrator agent — routes requests to specialized agents over A2A or answers them directly |
| `src/agentic_ai_infrastructure/a2a_database_agent.py` | A2A server wrapping a LangChain database agent (port 5001) |
| `src/agentic_ai_infrastructure/a2a_filesystem_agent.py` | A2A server wrapping a LangChain filesystem agent (port 5002) |
| `src/agentic_ai_infrastructure/sqlite_mcp_server.py` | Custom MCP server exposing SQLite tools |
| `src/agentic_ai_infrastructure/seed_db.py` | Seeds `demo.db` with sample products and orders |
| `langgraph.json` | LangGraph server config — points to the orchestrator graph |
| `sandbox/` | Sample files for the filesystem agent |
| `frontend/` | CopilotKit + Next.js app (scaffolded via `npx create-ag-ui-app`) |
| `pyproject.toml` | Python project and pinned dependencies (managed with uv) |
| `uv.lock` | Locked versions of all Python dependencies |

## Deeper dive into the functionality

### SQLite MCP Server (sqlite_mcp_server.py)

- This file implements a MCP server for exposing a local SQLite database functionalities.
- `FastMCP` is the high-level API from the MCP Python SDK for building MCP servers. It handles all the JSON-RPC protocol plumbing (serialization, request routing, and response formatting) for registered tools, resources and prompts.
- When creating a server, metadata can be defined through `instructions` that then can be passed to LLMs as context (tells the model what this server is for).
- The decorator `@mcp.tool()` registers the corresponding function as an MCP tool. The MCP SDK automatically:
  - Extracts the function name as the tool name
  - Uses the docstring as the tool description (which the LLM sees when deciding which tool to call)
  - Infers the required input schema from the function signature. The docstring's `Args` section is parsed by FastMCP to provide parameter descriptions to the LLM.
- Specifying `transport="stdio"` starts the MCP server using stdio transport. This means the server reads JSON-RPC requests from stdin and writes responses to stdout. It's not an HTTP server — it's a subprocess. The **Database Agent** launches this process and communicates with it over pipes. This is the standard MCP transport for local tools.
- Key insight: This file is purely an MCP server — it knows nothing about A2A, LangChain or the frontend. It is a self-contained tool provider. The `@mcp.tool()` decorator is the entire MCP integration — everything else is just SQLite logic. That is the point of MCP: tool authors write normal functions, the protocol handles the rest.

### Database AI Agent (a2a_database_agent.py)

- This file sits at the intersection of two protocols. From the outside, it is an A2A server — it speaks JSON-RPC, serves an `Agent Card`, receives questions over A2A from the **Orchestrator Agent** and streams responses via SSE. From the inside, it is an MCP client — it spawns **SQLite MCP server** to answer requests by calling its tools and uses an LLM to reason about the results. The LangChain ReAct agent is the glue between the two. Essentially, the MCP-client + Agent are wrapped inside of a A2A-compliant server.
- The `SYSTEM_PROMPT` instructs the LLM on how to behave during the conversation.
- `AgentExecutor` is the A2A SDKs abstract base class.
- `_ensure_agent(self)` ensures that the LangChain agent is only created on the first request. This is also where A2A and MCP connect:
  - `MultiServerMCPClient` configures the `SQLite MCP Server` connection.
  - When `get_tools()` is called, it spawns the SQLite MCP server (`python -m agentic_ai_infrastructure.sqlite_mcp_server`) as a subprocess, sends a `ListToolsRequest` over stdio, and gets back all the available tools of the MCP server.
  - `handle_tool_error = True` ensures tool errors are returned to the LLM as text rather than crashing the agent.
  - `create_agent()` builds the AI agent — an LLM that can reason about which tools to call, call them, observe the results and iterate until it has an answer.
- To properly utilize the `AgentExecutor` base class, the `execute()` method is implemented and the A2A framework calls it whenever a message arrives (`context` contains the incoming A2A message (the question from the **Orchestrator Agent**); `event_queue` is used to push events back to the caller (`TaskUpdater` is a convenience wrapper around the event queue)). This is the core — an A2A request comes in, the LLM reasons and calls MCP tools and the response streams back over A2A.
- `AgentSkill` defines what this agent can do. The `examples` help other agents (or humans) understand what kind of questions to send. This becomes part of the `Agent Card`.
- The `Agent Card` is the A2A discovery mechanism. It is served at `/.well-known/agent-card.json` and tells any A2A client: here is who I am, what I can do, where to reach me and that I support streaming. The **Orchestrator Agent** fetches this before sending any messages.
- Inside of `main()` the overall setup is done:
  - `DefaultRequestHandler` routes incoming A2A JSON-RPC requests to `DatabaseAgentExecutor`.
  - `A2AStarletteApplication` builds a Starlette ASGI app that serves the `Agent Card` and handles `message/send` and `message/stream` JSON-RPC endpoints.
  - `uvicorn` then serves this app as an HTTP server.

### Filesystem AI Agent (a2a_filesystem_agent.py)

This file is structurally identical to `a2a_database_agent.py`. The only differences are what MCP server it connects to and what it is specialized in. Only the key differences will be explained below:

- Instead of a database path, this agent knows about a directory. The `SANDBOX_DIR` is embedded into the system prompt so the LLM knows the boundaries of what it can access.
- Here, `MultiServerMCPClient` configures a connection to the prebuilt `Filesystem MCP Server`. Instead of spawning our own `sqlite_mcp_server.py`, it runs a `npx` command to spawn the prebuilt server `@modelcontextprotocol/server-filesystem`.

### Orchestrator AI Agent (orchestrator_agent.py)

The **Orchestrator Agent** is the central agent that talks to the user and delegates requests to specialized agents. Unlike the upper two agents, it does not utilize MCP at all. Its "tools" are A2A calls to the other agents. The **Orchestrator Agent** has no prior knowledge of **Database AI Agent** or **Filesystem AI Agent** - it discovers them through their Agent Cards and creates LangChain tools out of the information found there. Then, when a user request comes in, it delegates a task to one of the specialized agents if their capabilities are helpful for handling the request.

- `AGENT_URLS` is the only thing the orchestrator "knows" upfront — where to look for agents. It doesn't know what they do, what they're called, or what questions to send them. All of that comes from the Agent Cards.
- `_discover_agents()` is called on startup. Iterates over `AGENT_URLS` and fetches each agent's card at GET `{url}/.well-known/agent-card.json`. Returns a list of AgentCard objects containing everything the agent advertised — its name, description, skills, tags, examples. If an agent is unreachable, it prints a warning and skips it. The **Orchestrator Agent** still starts — it just won't have a tool for that agent.
- `_delegate()` implements the full A2A client flow - connects with the agent for streaming, sends a message, collects the response from SSE events. `ClientFactory.connect()` takes the `Agent Card` and creates an A2A client configured for that agent.
- `_make_tool_name(agent_name: str)` converts the agent's name from the card into a valid LangChain tool name. "Database Agent" becomes `ask_database_agent`, "Filesystem Agent" becomes `ask_filesystem_agent`. If someone adds a "Weather Agent", it would automatically become `ask_weather_agent`.
- `_build_tools(cards: list[AgentCard])` dynamically creates LangChain tools. The tool `description` — what the LLM reads when deciding which tool to call — is built entirely from the Agent Card's skills, descriptions, and examples. The LLM's routing knowledge comes from the agents themselves, not from manually written docstrings. `StructuredTool.from_function` creates a LangChain tool from a regular function — same as what `@tool` does, but programmatically so we can set the name and description from variables.
- `_build_system_prompt(cards: list[AgentCard])` pulls the tags (like database, sql, sqlite, query, schema) and examples (like "What tables are in the database?") from each agent's skills and compiles them into routing rules. The LLM sees this and knows how to route — but none of it manually written upfront. It all comes from the Agent Cards.
- The `SYSTEM_PROMPT` configures the routing logic. It is not hardcoded if/else branching — the LLM reads these rules and decides at runtime which tool to call (or none).
- `_cards = asyncio.run(_discover_agents())`  runs the async discovery synchronously at module import time. This happens once when `langgraph dev` loads the module. The agents must be running before the orchestrator starts — otherwise they won't be discovered.
- `create_agent()` builds an AI agent that loops between LLM reasoning and tool execution. The graph variable is referenced in `langgraph.json`. This graph variable is what `langgraph dev` imports and serves. This command loads this module, finds the graph object, wraps it in an HTTP API (threads, runs, streaming) and serves it on port 8123. The frontend's CopilotKit connects to that API.

### React Frontend (frontend/)

The frontend was scaffolded via the command `npx create-ag-ui-app@latest --langgraph-py`. This is a CLI tool from the AG-UI project that generates a Turborepo monorepo with a Next.js + CopilotKit frontend pre-wired for a LangGraph Python backend. It creates `frontend/` (Turborepo root with pnpm workspaces), `frontend/apps/app/` (Next.js app with CopilotKit already installed and configured) and `frontend/apps/agent/` (boilerplate Python LangGraph agent - deleted since a separate agent is defined with **Orchestrator Agent**).

From the scaffolded parts, some demo components were deleted and three files were customized:

`route.ts`: A Next.js API route that acts as a proxy between the browser and the LangGraph **Orchestrator Agent**.

- `LangGraphAgent` is CopilotKit's adapter for talking to a LangGraph server.
  - `deploymentUrl` — where the LangGraph server runs
  - `graphId` — which graph to use (matches the key in `langgraph.json`: "orchestrator")
- `CopilotRuntime` passes incoming POST requests to the defined `LangGraphAgent`. This then translates it into LangGraph API calls (create thread, send message, stream response). The LangGraph server runs the orchestrator graph. `LangGraphAgent` translates the LangGraph streaming events into AG-UI events (this is where AG-UI happens). Those AG-UI events stream back to the browser as server-sent events.

`layout.tsx`: This wraps the entire app in the CopilotKit context. `runtimeUrl="/api/copilotkit"` tells it where to send requests — that is the `route.ts` API endpoint. Every CopilotKit component inside this tree (like CopilotChat) will use this connection.

`page.tsx`: The chat UI.

- `useConfigureSuggestions` is a CopilotKit v2 hook that registers clickable suggestion pills in the chat UI. `available: "always"` means they show both before and after the first message. The component renders nothing visually — it just registers the suggestions with the CopilotKit context.
- `<CopilotChat />` is the entire chat UI — input box, message list, streaming responses, tool call visualization, suggestion pills. It's a pre-built CopilotKit component.

#### The full communication flow

```
Browser (React)
  │
  │  CopilotChat sends POST /api/copilotkit
  │  (CopilotKit internal protocol — not AG-UI yet)
  │
  ▼
Next.js API route (route.ts)
  │
  │  CopilotRuntime passes to LangGraphAgent
  │  LangGraphAgent calls LangGraph API:
  │    POST http://localhost:8123/threads  (create thread)
  │    POST http://localhost:8123/threads/{id}/runs/stream  (run graph)
  │
  ▼
LangGraph Server (port 8123)
  │
  │  Runs orchestrator_agent.py
  │  LLM decides to call ask_database_agent tool
  │  Tool calls _delegate("http://localhost:5001", question)
  │  A2A discovery + streaming happens here
  │
  ▼
Database Agent (port 5001)
  │
  │  Receives A2A message
  │  LLM calls MCP tools (list_tables, query)
  │  Streams response back via SSE
  │
  ▼ (response flows back up)

LangGraph Server
  │  Receives A2A response as tool result
  │  LLM generates final answer
  │  Streams tokens back to LangGraphAgent
  │
  ▼
Next.js API route
  │  LangGraphAgent translates LangGraph stream events
  │  into AG-UI events (TEXT_MESSAGE_CONTENT, TOOL_CALL_START, etc.)
  │  Streams them back to browser as SSE
  │
  ▼
Browser
  │  CopilotChat receives AG-UI events
  │  Renders text progressively, shows tool calls in sidebar
```

The AG-UI protocol is the last leg — between `route.ts` and the browser. No AG-UI encoding code is necessary. The `LangGraphAgent` adapter does the translation automatically: it takes LangGraph's native streaming format and converts it to AG-UI events (e.g. `TEXT_MESSAGE_CONTENT`, `TOOL_CALL_START` or `RUN_STARTED`).
