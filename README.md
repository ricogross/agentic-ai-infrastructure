# Agentic AI Infrastructure

[![checks](https://github.com/ricogross/agentic-ai-infrastructure/actions/workflows/checks.yaml/badge.svg)](https://github.com/ricogross/agentic-ai-infrastructure/actions/workflows/checks.yaml)

A reference multi-agent system that shows three open agentic protocols working together:

- **MCP** (Model Context Protocol) — agents access tools through MCP servers
- **A2A** (Agent-to-Agent) — an orchestrator agent delegates tasks to specialized agents over HTTP
- **AG-UI** (Agent-User Interaction) — the orchestrator streams what the agents do to a React frontend in real time

The project started as the proof of concept of a master's seminar paper. The paper and the slides are in [`docs/`](docs/). Since then, the code has been upgraded and hardened step by step; every change on `main` is its own pull request.

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
         │    accesses local    │                     │     reads local         │
         │    SQLite database   │                     │     directory           │
         │    → demo.db         │                     │     → sandbox/          │
         └──────────────────────┘                     └─────────────────────────┘
```

**Four processes** run at the same time (the ports are defaults, see [Configuration](#configuration)):

| Process | Started with | Port | Role |
|---------|--------------|------|------|
| Database Agent | `uv run database-agent` | 5001 | Answers questions about a SQLite database through a custom MCP server |
| Filesystem Agent | `uv run filesystem-agent` | 5002 | Browses and reads files through the prebuilt Filesystem MCP server |
| Orchestrator | `uv run langgraph dev --port 8123` | 8123 | LangGraph agent that answers directly or delegates over A2A |
| Frontend | `pnpm dev` in `frontend/` | 3000 | CopilotKit chat UI (Next.js) |

## How it works

1. **Discovery** — On first use, the orchestrator fetches the Agent Card of every agent in `AGENT_URLS`. For each agent it creates a tool (`ask_database_agent`, `ask_filesystem_agent`) and routing rules for its system prompt, both built from what the card advertises.

2. **LLM routing** — When the user sends a message, the orchestrator's LLM decides:
   - **Simple questions** → answer directly
   - **Database questions** → call `ask_database_agent` (A2A delegation)
   - **Filesystem questions** → call `ask_filesystem_agent` (A2A delegation)
   - **Cross-domain questions** → call both tools and combine the results

3. **Delegation** — A tool sends the question to its agent over A2A. The agent's own LLM calls the tools of its MCP server, and its answer streams back to the orchestrator as server-sent events.

4. **AG-UI streaming** — CopilotKit's `LangGraphAgent` adapter connects to the LangGraph server and translates its streaming events into AG-UI events for the React frontend. Tool calls, intermediate steps and streamed text all show up in the chat UI.

## Protocols

| Protocol | Transport | Where used |
|----------|-----------|------------|
| **AG-UI** | HTTP, server-sent events (via CopilotKit + LangGraph) | Frontend ↔ Orchestrator |
| **A2A** | HTTP, JSON-RPC 2.0, server-sent events (A2A 1.0) | Orchestrator → Specialized agents |
| **MCP** | stdio, JSON-RPC 2.0 | Specialized agent → Its MCP server |

## Getting started

### Prerequisites

- [uv](https://docs.astral.sh/uv/) (installs Python 3.14 automatically)
- Node.js 24+
- pnpm 11 or newer (`npm install -g pnpm@12`); the project pins its exact version in `frontend/package.json`, and pnpm switches to it by itself
- OpenAI API key

### Setup

```bash
# 1. Set up the Python backend (creates .venv from uv.lock)
uv sync

# 2. Create your .env from the template, then set OPENAI_API_KEY in it
cp .env.example .env

# 3. Seed the sample database
uv run seed-db

# 4. Set up the frontend
cd frontend
pnpm install
```

### Running the system

Start each service in its own terminal, in any order:

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

Then open http://localhost:3000, where the chat UI runs. The suggestions below the input box show what to ask, e.g. *"What files are in the sandbox? Read the meeting notes for me."*

## Configuration

Every setting has a default for running the whole system on one machine. The Python services read them from environment variables or from `.env` (template: `.env.example`, loaded by `config.py`); environment variables win.

| Setting | Default | Used by |
|---------|---------|---------|
| `OPENAI_API_KEY` | none, required | every LLM call |
| `MODEL` | `openai:gpt-4o-mini` | orchestrator and both agents, as `provider:model` for LangChain. Other providers need their LangChain package, e.g. `uv add langchain-anthropic` |
| `DATABASE_AGENT_PORT` | `5001` | Database Agent |
| `FILESYSTEM_AGENT_PORT` | `5002` | Filesystem Agent |
| `AGENT_URLS` | the two agents on `localhost` | orchestrator, comma-separated list of agents to discover |
| `LANGGRAPH_DEPLOYMENT_URL` | `http://localhost:8123` | frontend, to reach the orchestrator. It is not read from `.env`: set it in the shell before `pnpm dev` or in `frontend/apps/app/.env.local`. It has to match the `--port` of `langgraph dev` |

## Security and guardrails

The agents act on an LLM's decisions, so the tools they get are restricted at the source, not only in the prompt:

- **Database** — The SQLite MCP server opens `demo.db` read-only, and a SQLite authorizer lets `query` only read. SQLite itself rejects writes, `PRAGMA`, `ATTACH` and `VACUUM INTO`. Every query stops after `QUERY_TIME_LIMIT` seconds, so a slow query can't block the server.
- **Filesystem** — The Filesystem MCP server runs with `--read-only` and only sees `sandbox/`. Its version is pinned, so no new release (and no new tool) arrives unnoticed.
- **Secrets** — `.env` is not committed. The MCP SDK starts MCP servers with only a short list of safe environment variables (e.g. `PATH`), so the OpenAI API key never reaches them. A `gitleaks` hook scans every commit for secrets.
- **Supply chain** — `uv.lock` and `pnpm-lock.yaml` pin every dependency, and CI installs exactly those versions. pnpm runs no install scripts of dependencies unless `frontend/pnpm-workspace.yaml` allows them (none are allowed). The CI workflows only get read access to the repository.

## Development

Ruff (lint and format) and ty (type checks) are dev dependencies and come with `uv sync`:

```bash
uv run ruff check     # lint
uv run ruff format    # format
uv run ty check       # type-check
```

The frontend has its own checks, run in `frontend/`:

```bash
pnpm lint             # ESLint with the Next.js rules
pnpm build            # production build, including the TypeScript check
```

The pre-commit hooks run the Python checks, file hygiene, a secret scan and a Conventional Commits check of the commit message:

```bash
uv run pre-commit install           # once per clone, installs the pre-commit and commit-msg hooks
uv run pre-commit run --all-files   # run all hooks by hand
```

Changes reach `main` only through pull requests, which are squash-merged. A pull request needs three passing checks:

| Check | Workflow | What it does |
|-------|----------|--------------|
| `pre-commit` | `.github/workflows/checks.yaml` | runs all pre-commit hooks on the whole repository |
| `frontend` | `.github/workflows/checks.yaml` | installs the frontend from the lockfile, runs `pnpm lint` and `pnpm build` |
| `pr-title` | `.github/workflows/pr-title.yaml` | checks that the pull request title is a Conventional Commit, because GitHub uses it as the message of the squash commit |

Branches are named `type/short-description`, e.g. `fix/sqlite-time-limit`, with the same types as the commit messages.

## Known limitations

- **No automated tests yet.** Changes are checked with ad-hoc scripts and end-to-end runs; CI only lints, type-checks and builds.
- **mcp 2.x is not possible yet.** `langchain-mcp-adapters` still requires `mcp<2`, which also keeps `langgraph-api` below 0.18.
- **A crashed MCP server is not restarted.** The agents keep one session to each MCP server open; if a server dies, restart its agent.
- **`localhost` is slow on Windows.** It resolves to IPv6 (`::1`) first, while the agents only listen on `127.0.0.1`, which adds about 0.4 s to every new connection to an agent.
- **CopilotKit warns about threads.** Its runtime logs that listing and clearing threads needs a caller identity; those endpoints answer 403, the chat itself is not affected.

## Project structure

| Path | Purpose |
|------|---------|
| `src/agentic_ai_infrastructure/` | Python package with all backend code (`PROJECT_ROOT` in `__init__.py`) |
| `src/agentic_ai_infrastructure/orchestrator_agent.py` | LangGraph orchestrator agent — routes requests to specialized agents over A2A or answers them directly |
| `src/agentic_ai_infrastructure/config.py` | Settings from environment variables and `.env` (see [Configuration](#configuration)) |
| `src/agentic_ai_infrastructure/a2a_mcp_agent.py` | Shared A2A server for both agents: executor, Agent Card and startup |
| `src/agentic_ai_infrastructure/a2a_database_agent.py` | A2A server wrapping a LangChain database agent (port 5001) |
| `src/agentic_ai_infrastructure/a2a_filesystem_agent.py` | A2A server wrapping a LangChain filesystem agent (port 5002) |
| `src/agentic_ai_infrastructure/sqlite_mcp_server.py` | Custom MCP server exposing SQLite tools |
| `src/agentic_ai_infrastructure/seed_db.py` | Seeds `demo.db` with sample products and orders |
| `sandbox/` | Sample files for the filesystem agent (`notes/`, `data/config.json`) |
| `frontend/` | CopilotKit + Next.js app (scaffolded via `npx create-ag-ui-app`) |
| `docs/` | The seminar paper and the slides (PDF) |
| `langgraph.json` | LangGraph server config — points to the orchestrator's graph factory |
| `.env.example` | Template for `.env`: the OpenAI API key and all optional settings |
| `pyproject.toml`, `uv.lock` | Python project, dependencies and their locked versions (managed with uv) |
| `.pre-commit-config.yaml` | Hooks for every commit (see [Development](#development)) |
| `.github/workflows/` | CI: `checks.yaml` and `pr-title.yaml` |
| `.vscode/` | Editor settings and recommended extensions (Python, Ruff, ty, YAML, TOML) |

Running the system creates `demo.db` (by `uv run seed-db`) and one `<name>_mcp_server.log` per MCP server with its stderr. Both are ignored by Git.

## Deeper dive into the functionality

### SQLite MCP Server (sqlite_mcp_server.py)

- This file implements an MCP server that exposes a local SQLite database.
- `FastMCP` is the high-level API from the MCP Python SDK for building MCP servers. It handles all the JSON-RPC protocol plumbing (serialization, request routing, and response formatting) for registered tools, resources and prompts.
- When creating a server, metadata can be defined through `instructions` that then can be passed to LLMs as context (tells the model what this server is for).
- The decorator `@mcp.tool()` registers the corresponding function as an MCP tool. The MCP SDK automatically:
  - Extracts the function name as the tool name
  - Uses the docstring as the tool description (which the LLM sees when deciding which tool to call)
  - Infers the required input schema from the function signature. The docstring's `Args` section is parsed by FastMCP to provide parameter descriptions to the LLM.
- Specifying `transport="stdio"` starts the MCP server using stdio transport. This means the server reads JSON-RPC requests from stdin and writes responses to stdout. It's not an HTTP server — it's a subprocess. The **Database Agent** launches this process and communicates with it over pipes. This is the standard MCP transport for local tools.
- Tool failures are raised as `ToolError`. FastMCP then marks the result as an error (`isError`), so the agent sees a failed tool call instead of a normal answer that happens to contain an error message.
- The database is opened read-only (`mode=ro`), and `query` additionally installs a SQLite *authorizer* that only permits reading. That way SQLite itself rejects writes, `PRAGMA`, `ATTACH` and `VACUUM INTO`, instead of a check on the beginning of the SQL text. Recursive queries (`WITH RECURSIVE`) only read and are allowed.
- `query` also stops every query after `QUERY_TIME_LIMIT` seconds, using a SQLite progress handler. A query that only reads can still run for hours, e.g. a cross join of many tables or a recursive query that never ends, and while it runs, the server answers no other tool call.
- Key insight: This file is purely an MCP server — it knows nothing about A2A, LangChain or the frontend. It is a self-contained tool provider. The `@mcp.tool()` decorator is the entire MCP integration — everything else is just SQLite logic. That is the point of MCP: tool authors write normal functions, the protocol handles the rest.

### Shared A2A agent server (a2a_mcp_agent.py)

- This file sits at the intersection of two protocols. From the outside, an agent built from it is an A2A server — it speaks JSON-RPC, serves an `Agent Card`, receives questions over A2A from the **Orchestrator Agent** and streams responses via SSE. From the inside, it is an MCP client — it spawns MCP servers to answer requests by calling their tools and uses an LLM to reason about the results. The LangChain ReAct agent is the glue between the two. Both specialized agents are built from this file and only define what differs: their MCP servers, their system prompt and their skill.
- `AgentExecutor` is the A2A SDK's abstract base class. `McpAgentExecutor` implements it for a given set of MCP servers (`mcp_servers`), a `system_prompt` and a `model`.
- `connected()` starts the MCP servers and builds the LangChain agent. `serve()` runs it as the app's `lifespan`, so this happens once when the agent starts, and the servers stop again when it shuts down. This is also where A2A and MCP connect:
  - `stdio_client()` spawns each MCP server as a subprocess and talks to it over stdin/stdout. The server's stderr goes to a log file, `<name>_mcp_server.log` in the project root.
  - `ClientSession` keeps one MCP session to each server open for all requests. `load_mcp_tools()` sends a `ListToolsRequest` and turns every tool of the server into a LangChain tool that calls it over this session.
  - `handle_tool_error = True` ensures tool errors are returned to the LLM as text rather than crashing the agent.
  - `create_agent()` builds the AI agent — an LLM that can reason about which tools to call, call them, observe the results and iterate until it has an answer.
- `execute()` implements the `AgentExecutor` base class: the A2A framework calls it whenever a message arrives. `context` contains the incoming A2A message (the question from the **Orchestrator Agent**), and `event_queue` is used to push events back to the caller (`TaskUpdater` is a convenience wrapper around the event queue). Since A2A 1.0, the events of a task have to start with the task itself, so `execute()` creates it first (`new_task_from_user_message()`). This is the core — an A2A request comes in, the LLM reasons and calls MCP tools and the response streams back over A2A.
- `build_agent_card()` builds the `Agent Card`, the A2A discovery mechanism. It is served at `/.well-known/agent-card.json` and tells any A2A client: here is who I am, what I can do, where to reach me and that I support streaming. The **Orchestrator Agent** fetches this before sending any messages.
- `serve()` does the overall setup:
  - `DefaultRequestHandler` routes incoming A2A JSON-RPC requests to the executor.
  - `create_agent_card_routes()` and `create_jsonrpc_routes()` create the routes that serve the `Agent Card` and handle the `SendMessage` and `SendStreamingMessage` JSON-RPC methods. `Starlette` combines them into an ASGI app.
  - `uvicorn` then serves this app as an HTTP server.

### Database AI Agent (a2a_database_agent.py)

- The `SYSTEM_PROMPT` instructs the LLM on how to behave during the conversation.
- `MCP_SERVERS` configures a single MCP server: the **SQLite MCP server**, started as `python -m agentic_ai_infrastructure.sqlite_mcp_server`.
- `AgentSkill` defines what this agent can do. The `examples` help other agents (or humans) understand what kind of questions to send. `build_agent_card()` puts it into the `Agent Card`.
- `main()` hands the `Agent Card` and a `McpAgentExecutor` with these settings to `serve()`.

### Filesystem AI Agent (a2a_filesystem_agent.py)

This file is structured like `a2a_database_agent.py`. The only differences are what MCP server it connects to and what it is specialized in:

- Instead of a database path, this agent knows about a directory. The `SANDBOX_DIR` is embedded into the system prompt so the LLM knows the boundaries of what it can access.
- Here, `MCP_SERVERS` configures a connection to the prebuilt `Filesystem MCP Server`. Instead of spawning our own `sqlite_mcp_server.py`, it runs a `npx` command to spawn the prebuilt server `@modelcontextprotocol/server-filesystem`. Its version is pinned in `FILESYSTEM_SERVER`, so every start runs the same server. `--read-only` makes the server offer only its reading tools, so the agent can browse and read the sandbox but not change it, as its Agent Card says.

### Orchestrator AI Agent (orchestrator_agent.py)

The **Orchestrator Agent** is the central agent that talks to the user and delegates requests to specialized agents. Unlike the two agents above, it does not use MCP at all. Its "tools" are A2A calls to the other agents. The **Orchestrator Agent** has no prior knowledge of the **Database AI Agent** or the **Filesystem AI Agent** — it discovers them through their Agent Cards and creates LangChain tools out of the information found there. Then, when a user request comes in, it delegates a task to one of the specialized agents if their capabilities are helpful for handling the request.

- The `AGENT_URLS` setting is the only thing the orchestrator "knows" upfront — where to look for agents. It doesn't know what they do, what they're called, or what questions to send them. All of that comes from the Agent Cards.
- `_discover_agents()` is called by `make_graph()`. Iterates over `AGENT_URLS` and fetches each agent's card at GET `{url}/.well-known/agent-card.json`. Returns a list of AgentCard objects containing everything the agent advertised — its name, description, skills, tags, examples. If an agent is unreachable, it prints a warning and skips it. The **Orchestrator Agent** still works — it just won't have a tool for that agent until the agent is reachable.
- `_delegate()` implements the full A2A client flow — connects with the agent for streaming, sends a message, collects the response from SSE events. `create_client()` takes the `Agent Card` from the discovery and creates an A2A client configured for that agent.
- `_make_tool_name(agent_name: str)` converts the agent's name from the card into a valid LangChain tool name. "Database Agent" becomes `ask_database_agent`, "Filesystem Agent" becomes `ask_filesystem_agent`. If someone adds a "Weather Agent", it would automatically become `ask_weather_agent`.
- `_build_tools(cards: list[AgentCard])` dynamically creates LangChain tools. The tool `description` — what the LLM reads when deciding which tool to call — is built entirely from the Agent Card's skills, descriptions, and examples. The LLM's routing knowledge comes from the agents themselves, not from manually written docstrings. `StructuredTool.from_function` creates a LangChain tool from a regular function — same as what `@tool` does, but programmatically so we can set the name and description from variables.
- `_build_system_prompt(cards: list[AgentCard])` pulls the tags (like database, sql, sqlite, query, schema) and examples (like "What tables are in the database?") from each agent's skills and compiles them into routing rules. The LLM sees this and knows how to route — but none of it is manually written upfront. It all comes from the Agent Cards. It is not hardcoded if/else branching — the LLM reads these rules and decides at runtime which tool to call (or none).
- `make_graph()` is a *graph factory*: `langgraph.json` points to it, and `langgraph dev` calls it whenever it needs the graph. It discovers the agents, builds the tools and the system prompt from their cards, and `create_agent()` builds an AI agent that loops between LLM reasoning and tool execution. Because the discovery happens on first use instead of when the module is imported, the agents and `langgraph dev` can start in any order. Once every agent in `AGENT_URLS` has answered, the graph is kept; until then, every call looks for the missing agents again.
- `langgraph dev` wraps the graph in an HTTP API (threads, runs, streaming) and serves it on port 8123. The frontend's CopilotKit connects to that API.

### React Frontend (frontend/)

The frontend was scaffolded via the command `npx create-ag-ui-app@latest --langgraph-py`. This is a CLI tool from the AG-UI project that generates a Turborepo monorepo with a Next.js + CopilotKit frontend pre-wired for a LangGraph Python backend. It creates `frontend/` (Turborepo root with pnpm workspaces), `frontend/apps/app/` (Next.js app with CopilotKit already installed and configured) and `frontend/apps/agent/` (boilerplate Python LangGraph agent — deleted, since the **Orchestrator Agent** takes its place).

From the scaffolded parts, some demo components were deleted and three files were customized:

`route.ts`: A Next.js API route that acts as a proxy between the browser and the LangGraph **Orchestrator Agent**.

- `LangGraphAgent` is CopilotKit's adapter for talking to a LangGraph server.
  - `deploymentUrl` — where the LangGraph server runs
  - `graphId` — which graph to use (matches the key in `langgraph.json`: "orchestrator")
- `CopilotRuntime` passes incoming POST requests to the defined `LangGraphAgent`. This then translates it into LangGraph API calls (create thread, send message, stream response). The LangGraph server runs the orchestrator graph. `LangGraphAgent` translates the LangGraph streaming events into AG-UI events (this is where AG-UI happens). Those AG-UI events stream back to the browser as server-sent events.

`layout.tsx`: This wraps the entire app in the CopilotKit context. `runtimeUrl="/api/copilotkit"` tells it where to send requests — that is the `route.ts` API endpoint. Every CopilotKit component inside this tree (like CopilotChat) will use this connection. `useSingleEndpoint` tells CopilotKit that `route.ts` answers every request on this one URL, so it doesn't probe `/api/copilotkit/info` first (which would end in a 404).

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
  │  Runs the graph from make_graph() (agents discovered on first use)
  │  LLM decides to call ask_database_agent tool
  │  Tool calls _delegate(card, question)
  │  A2A request + streamed response happen here
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
  │  Renders text progressively, shows tool calls in the chat
```

The AG-UI protocol is the last leg — between `route.ts` and the browser. No AG-UI encoding code is necessary. The `LangGraphAgent` adapter does the translation automatically: it takes LangGraph's native streaming format and converts it to AG-UI events (e.g. `TEXT_MESSAGE_CONTENT`, `TOOL_CALL_START` or `RUN_STARTED`).

## License

[MIT](LICENSE)
