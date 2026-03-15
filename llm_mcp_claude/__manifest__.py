{
    "name": "LLM MCP Claude",
    "version": "18.0.1.0.0",
    "category": "Technical",
    "summary": "Claude Code MCP server integration for Odoo LLM",
    "description": """
        LLM MCP Claude

        Registers the Claude Code MCP server as a pre-configured external tool source
        for Odoo AI assistants.

        Depends on llm_mcp_client for the MCP client infrastructure.
        Provides:
          • Claude Code stdio MCP server record (claude-code-mcp)
    """,
    "author": "Apexive Solutions LLC",
    "website": "https://github.com/apexive/odoo-llm",
    "license": "LGPL-3",
    "depends": ["llm_mcp_client"],
    "data": [
        "data/llm_mcp_claude_servers.xml",
    ],
    "auto_install": False,
    "application": False,
    "installable": True,
}
