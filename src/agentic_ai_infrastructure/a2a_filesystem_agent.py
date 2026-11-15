from a2a.types import AgentSkill
from dotenv import load_dotenv
from mcp import StdioServerParameters

from agentic_ai_infrastructure import PROJECT_ROOT
from agentic_ai_infrastructure.a2a_mcp_agent import McpAgentExecutor, build_agent_card, serve

load_dotenv()

SANDBOX_DIR = str(PROJECT_ROOT / "sandbox")
# Pinned: without a version, `npx -y` runs whatever npm published last, on every start.
FILESYSTEM_SERVER = "@modelcontextprotocol/server-filesystem@2.3.0"

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

MCP_SERVERS = {
    "filesystem": StdioServerParameters(
        command="npx",
        args=[
            "-y",
            FILESYSTEM_SERVER,
            # Serve only the tools that read, e.g. no write_file or move_file.
            "--read-only",
            SANDBOX_DIR,
        ],
    ),
}

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

agent_card = build_agent_card(
    name="Filesystem Agent",
    description="A specialized agent for browsing and reading files in a sandboxed "
    "directory containing notes and configuration files.",
    skill=skill,
    port=PORT,
)


def main():
    serve(agent_card, McpAgentExecutor(MCP_SERVERS, SYSTEM_PROMPT), PORT)


if __name__ == "__main__":
    main()
