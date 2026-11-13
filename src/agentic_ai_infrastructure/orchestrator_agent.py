"""
Orchestrator LangGraph Agent.

On startup, discovers all A2A sub-agents by fetching their Agent Cards.
The sub-agents are registered through the AGENT_URLS config variable.
Dynamically generates LangChain tools and routing instructions from
the discovered skills.

"""

import asyncio
import re

import httpx
from a2a.client import (
    A2ACardResolver,
    ClientConfig,
    ClientFactory,
    create_text_message_object,
)
from a2a.types import AgentCard
from a2a.types import Message as A2AMessage
from a2a.utils import get_message_text
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import StructuredTool

load_dotenv()


AGENT_URLS = [
    "http://localhost:5001",
    "http://localhost:5002",
]

MODEL = "openai:gpt-4o-mini"


async def _discover_agents() -> list[AgentCard]:
    """Fetch Agent Cards from all known agent URLs."""
    cards: list[AgentCard] = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as http_client:
        for url in AGENT_URLS:
            try:
                resolver = A2ACardResolver(httpx_client=http_client, base_url=url)
                card = await resolver.get_agent_card()
                cards.append(card)
                skills = ", ".join(s.id for s in (card.skills or []))
                print(
                    f"[A2A] Discovered: {card.name} at {url} (skills: {skills})",
                    flush=True,
                )
            except Exception as e:
                print(f"[A2A] Warning: could not reach {url}: {e}", flush=True)
    return cards


async def _delegate(url: str, agent_name: str, question: str) -> str:
    """Send a question to a A2A agent and return the final response."""
    print(f"[A2A] Delegating to {agent_name}: {question!r}", flush=True)

    async with httpx.AsyncClient() as http_client:
        resolver = A2ACardResolver(httpx_client=http_client, base_url=url)
        card = await resolver.get_agent_card()

    a2a_http = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
    config = ClientConfig(streaming=True, httpx_client=a2a_http)
    client = await ClientFactory.connect(card, client_config=config)
    try:
        message = create_text_message_object(content=question)
        response_text = ""
        event_count = 0
        async for event in client.send_message(message):
            event_count += 1
            if isinstance(event, A2AMessage):
                response_text = get_message_text(event)
            else:
                task, _ = event
                if task.status and task.status.message:
                    response_text = get_message_text(task.status.message)
        print(
            f"[A2A] Response from {agent_name} ({event_count} SSE events, {len(response_text)} chars)",
            flush=True,
        )
        return response_text or "(Agent returned no response)"
    finally:
        await client.close()


def _make_tool_name(agent_name: str) -> str:
    """Convert an agent name like 'Database Agent' to 'ask_database_agent'."""
    slug = re.sub(r"[^a-z0-9]+", "_", agent_name.lower()).strip("_")
    return f"ask_{slug}"


def _build_tools(cards: list[AgentCard]) -> list[StructuredTool]:
    """Create a LangChain tool for each discovered agent, using the Agent Card
    metadata for the tool name, description, and routing."""
    tools = []
    for card in cards:
        url = card.url.rstrip("/")
        name = _make_tool_name(card.name)
        agent_name = card.name

        # Build tool description from the card's skills
        skill_lines = []
        for skill in card.skills or []:
            skill_lines.append(f"- {skill.name}: {skill.description}")
            if skill.examples:
                examples = "; ".join(skill.examples[:3])
                skill_lines.append(f"  Examples: {examples}")

        description = (
            f"Delegate a question to the {card.name}.\n"
            f"{card.description}\n\n"
            f"Skills:\n" + "\n".join(skill_lines)
        )

        # Create an async function that delegates to this agent
        async def _call(question: str, _url=url, _name=agent_name) -> str:
            return await _delegate(_url, _name, question)

        tool = StructuredTool.from_function(
            coroutine=_call,
            name=name,
            description=description,
            handle_tool_error=True,
        )
        tools.append(tool)
        print(f"[A2A] Registered tool: {name}", flush=True)

    return tools


def _build_system_prompt(cards: list[AgentCard]) -> str:
    """Generate the orchestrator's system prompt from discovered Agent Cards."""
    agent_descriptions = []
    for card in cards:
        tool_name = _make_tool_name(card.name)
        tags = set()
        examples = []
        for skill in card.skills or []:
            tags.update(skill.tags or [])
            examples.extend(skill.examples or [])
        tag_str = ", ".join(sorted(tags))
        example_str = "; ".join(examples[:4])
        agent_descriptions.append(
            f"- For questions about {tag_str} — use the {tool_name} tool. (e.g. {example_str})"
        )

    routing_rules = "\n".join(agent_descriptions)

    return (
        "You are an orchestrator assistant. You help users by either answering "
        "directly or delegating to specialized agents.\n\n"
        "Routing rules:\n"
        "1. For greetings, general knowledge, or simple questions — answer directly.\n"
        f"{routing_rules}\n"
        f"{len(cards) + 1}. If the user's question spans multiple domains, "
        "call multiple tools and synthesize the results.\n"
        f"{len(cards) + 2}. Always present the delegated agent's response clearly. "
        "Do not fabricate data."
    )


print("[A2A] Discovering agents...", flush=True)
_cards = asyncio.run(_discover_agents())

if not _cards:
    print(
        "[A2A] WARNING: No agents discovered. The orchestrator will have no tools.",
        flush=True,
    )

_tools = _build_tools(_cards)
_system_prompt = _build_system_prompt(_cards)

print(f"[A2A] System prompt:\n{_system_prompt}\n", flush=True)

graph = create_agent(MODEL, _tools, system_prompt=_system_prompt)
