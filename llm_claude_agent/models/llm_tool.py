"""
llm.tool extension for implementation='claude_agent'
"""

import asyncio
import concurrent.futures
import logging
import os

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_TOOLS = "Read,Edit,MultiEdit,Write,Bash,Glob,Grep,LS"

_CLAUDE_CLI_CANDIDATES = [
    os.environ.get("CLAUDE_BIN", ""),
    "/usr/local/bin/claude",
    "/usr/bin/claude",
    "/root/.nvm/versions/node/v23.10.0/bin/claude",
]


def _find_claude_cli():
    import shutil
    for path in _CLAUDE_CLI_CANDIDATES:
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return shutil.which("claude")


class LLMTool(models.Model):
    _inherit = "llm.tool"

    claude_work_folder = fields.Char(
        string="Work Folder",
        help="Absolute path inside the container for Claude Code's working directory.",
    )
    claude_allowed_tools = fields.Char(
        string="Allowed Tools",
        default=DEFAULT_ALLOWED_TOOLS,
        help="Comma-separated list of Claude Code built-in tools to allow.",
    )
    claude_permission_mode = fields.Selection(
        [
            ("default", "Default (ask for confirmation)"),
            ("acceptEdits", "Accept Edits (auto-approve file changes)"),
            ("bypassPermissions", "Bypass Permissions (no prompts — dangerous)"),
        ],
        string="Permission Mode",
        default="acceptEdits",
    )
    claude_system_prompt = fields.Text(string="System Prompt")

    @api.model
    def _get_available_implementations(self):
        impls = super()._get_available_implementations()
        return impls + [("claude_agent", "Claude Agent SDK")]

    def execute(self, parameters):
        if self.implementation == "claude_agent":
            self.ensure_one()
            return self.claude_agent_execute(**parameters)
        return super().execute(parameters)

    def _get_implementation_method(self):
        if self.implementation == "claude_agent":
            return self.claude_agent_execute
        return super()._get_implementation_method()

    def get_input_schema(self):
        if self.implementation == "claude_agent":
            return {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Natural-language prompt for Claude Code to execute.",
                    }
                },
                "required": ["prompt"],
            }
        return super().get_input_schema()

    def claude_agent_execute(self, prompt: str) -> str:
        self.ensure_one()

        try:
            from claude_agent_sdk import ClaudeAgentOptions
        except ImportError:
            raise UserError(
                _("The 'claude-agent-sdk' Python package is not installed.")
            )

        cli_path = _find_claude_cli()
        if not cli_path:
            raise UserError(
                _("The 'claude' CLI was not found. Checked: %s")
                % ", ".join(c for c in _CLAUDE_CLI_CANDIDATES if c)
            )

        _logger.info("Claude Agent using CLI: %s", cli_path)

        stderr_lines = []

        def _on_stderr(line: str):
            stderr_lines.append(line)
            _logger.warning("Claude CLI stderr: %s", line.rstrip())

        options_kwargs = {
            "cli_path": cli_path,
            # Only override HOME and CLAUDE_HOME — the SDK merges this with
            # the current environment, it does NOT replace it entirely.
            "env": {
                "HOME": "/root",
                "CLAUDE_HOME": "/root/.claude",
            },
            "stderr": _on_stderr,
        }

        allowed = self.claude_allowed_tools or DEFAULT_ALLOWED_TOOLS
        if allowed.strip():
            options_kwargs["allowed_tools"] = [
                t.strip() for t in allowed.split(",") if t.strip()
            ]

        if self.claude_permission_mode:
            options_kwargs["permission_mode"] = self.claude_permission_mode

        if self.claude_system_prompt and self.claude_system_prompt.strip():
            options_kwargs["system_prompt"] = self.claude_system_prompt.strip()

        if self.claude_work_folder and self.claude_work_folder.strip():
            options_kwargs["cwd"] = self.claude_work_folder.strip()

        options = ClaudeAgentOptions(**options_kwargs)

        _logger.info(
            "Claude Agent tool '%s' starting. work_folder=%s prompt=%s...",
            self.name,
            self.claude_work_folder or "(default)",
            prompt[:120],
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run_claude_agent_sync, prompt, options)
            try:
                result_text = future.result()
            except Exception as e:
                stderr_dump = "".join(stderr_lines)
                raise UserError(
                    _("Claude Agent execution failed: %s\nstderr: %s")
                    % (str(e), stderr_dump or "(empty)")
                )

        _logger.info(
            "Claude Agent tool '%s' finished. result length=%d",
            self.name,
            len(result_text),
        )
        return result_text


def _run_claude_agent_sync(prompt: str, options) -> str:
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, query

    async def _run():
        collected = []
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        collected.append(block.text)
                    elif hasattr(block, "text"):
                        collected.append(block.text)
            elif isinstance(message, ResultMessage):
                if message.result:
                    collected.append(message.result)
        return "\n".join(collected).strip()

    return asyncio.run(_run())
