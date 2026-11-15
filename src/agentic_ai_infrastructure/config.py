"""Settings, read from environment variables or the .env file in the project root.

Every setting has a default for running the whole system on one machine, so .env only
needs the OpenAI API key. Environment variables win over .env. .env.example lists them all.
"""

import os

from dotenv import load_dotenv

from agentic_ai_infrastructure import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env", interpolate=False)

# LLM of the orchestrator and both agents, as "provider:model" for LangChain. Providers other
# than OpenAI need their LangChain package, e.g. `uv add langchain-anthropic`.
MODEL = os.getenv("MODEL", "openai:gpt-4o-mini")

DATABASE_AGENT_PORT = int(os.getenv("DATABASE_AGENT_PORT", "5001"))
FILESYSTEM_AGENT_PORT = int(os.getenv("FILESYSTEM_AGENT_PORT", "5002"))

# Where the orchestrator looks for agents, comma-separated. Defaults to the two agents above.
AGENT_URLS = [
    url.strip()
    for url in os.getenv(
        "AGENT_URLS",
        f"http://localhost:{DATABASE_AGENT_PORT},http://localhost:{FILESYSTEM_AGENT_PORT}",
    ).split(",")
    if url.strip()
]
