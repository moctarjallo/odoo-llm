{
    "name": "LLM Claude Agent",
    "version": "18.0.1.0.0",
    "category": "Technical",
    "summary": "Claude Agent SDK integration for Odoo LLM tools",
    "description": """
        LLM Claude Agent

        Adds a ``claude_agent`` implementation to ``llm.tool`` that invokes
        Claude Code programmatically via the ``claude-agent-sdk`` Python package.

        Authentication is handled by the mounted ~/.claude credentials
        (subscription auth — no API key required), or falls back to
        ANTHROPIC_API_KEY if set in the environment.

        Key features:
          • Works with Claude Pro/Max subscription (no API key billing)
          • Configurable work folder, allowed tools, and permission mode
          • Returns full streamed output as a single text result
          • Async execution bridged into Odoo's synchronous worker via asyncio

        Provides:
          • claude_agent implementation on llm.tool
          • Pre-configured llm_tool_claude_agent record pointing at
            /workspace/ordomatics/addons/odoo-llm
    """,
    "author": "Kajandé",
    "license": "LGPL-3",
    "depends": ["llm_tool"],
    "data": [
        "data/llm_claude_agent_tool.xml",
    ],
    "external_dependencies": {
        "python": ["claude_agent_sdk"],
    },
    "auto_install": False,
    "application": False,
    "installable": True,
}
