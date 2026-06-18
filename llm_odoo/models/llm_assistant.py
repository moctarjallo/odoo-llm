# -*- coding: utf-8 -*-

import json
import logging
import re

from odoo import fields, models

_logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)
_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


class LlmAssistant(models.Model):
    _inherit = "llm.assistant"

    auto_pipeline = fields.Boolean(
        string="Drive Business Pipeline",
        default=False,
        help="Run AI business-pipeline automation (CRM qualification, sales "
        "proposals, …) on inbound messages for threads using this assistant.",
    )

    def structured_chat(self, tag, user_content):
        """One-shot structured LLM call: send `[{tag}]\\n\\n{user_content}` plus this
        assistant's system prompt, with no thread/history and no tools, and parse
        the response as JSON.

        This is the C layer's *decision* primitive — distinct from the
        conversational ``chat()``/``generate()`` used to talk to the customer.

        Returns the parsed JSON value (typically a dict), or None if the assistant
        has no model/provider configured or the call/parsing fails.
        """
        self.ensure_one()
        if not self.model_id or not self.model_id.provider_id:
            _logger.debug(
                "structured_chat: no model/provider on assistant %s — skipping",
                self.name,
            )
            return None

        provider = self.model_id.provider_id
        system_prompt = self.prompt_id.template if self.prompt_id else ""

        try:
            response = provider.chat(
                messages=self.env["mail.message"],
                model=self.model_id,
                prepend_messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"[{tag}]\n\n{user_content}"},
                ],
                stream=False,
            )
            if isinstance(response, dict):
                response = response.get("content", "") or ""
            elif not isinstance(response, str):
                response = "".join(
                    (c.get("content", "") if isinstance(c, dict) else str(c))
                    for c in response
                )
            text = _FENCE_RE.sub("", response).strip()
            match = _JSON_OBJ_RE.search(text)
            return json.loads(match.group() if match else text)
        except Exception:
            _logger.warning(
                "structured_chat [%s] failed for assistant %s",
                tag,
                self.name,
                exc_info=True,
            )
            return None
