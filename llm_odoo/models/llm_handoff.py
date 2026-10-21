# -*- coding: utf-8 -*-

from odoo import models
from odoo.addons.llm_tool.decorators import llm_tool


class LLMHandoffTools(models.TransientModel):
    _name = "llm.handoff.tools"
    _description = "LLM Handoff Tools"

    @llm_tool
    def llm_hand_off(self, assistant: str, reason: str) -> dict:
        """Hand the conversation to an allowed specialized assistant."""
        message = self.env.context.get("message")
        if not message or message.model != "llm.thread" or not message.res_id:
            return {"success": False, "error": "No conversation thread is available."}

        thread = self.env["llm.thread"].browse(message.res_id).exists()
        if not thread or not thread.assistant_id:
            return {"success": False, "error": "No current assistant is available."}

        target = thread.assistant_id.handoff_assistant_ids.filtered(
            lambda candidate: candidate.active and candidate.code == assistant
        )[:1]
        if not target:
            return {"success": False, "error": "That assistant is not an allowed handoff target."}
        if target == thread.assistant_id:
            return {"success": False, "error": "The conversation is already with that assistant."}
        if not thread._handoff_target_allowed(target):
            return {"success": False, "error": "That assistant is not routed for this conversation."}

        Message = self.env["mail.message"].sudo()
        last_user = Message.search([
            ("model", "=", "llm.thread"),
            ("res_id", "=", thread.id),
            ("llm_role", "=", "user"),
        ], order="id desc", limit=1)
        if not last_user:
            return {"success": False, "error": "There is no contact message to hand off."}

        prior_handoffs = Message.search([
            ("model", "=", "llm.thread"),
            ("res_id", "=", thread.id),
            ("llm_role", "=", "tool"),
            ("id", ">", last_user.id),
            # The tool executor passes the current tool message in context.
            # Exclude it: otherwise the handoff call sees its own pending
            # tool message and rejects the first handoff of every turn.
            ("id", "!=", message.id),
        ])
        if prior_handoffs.filtered(
            lambda tool: (tool.body_json or {}).get("tool_name") == "llm_hand_off"
        ):
            return {"success": False, "error": "This turn already handed off once."}

        thread.set_assistant(target.id)
        return {
            "success": True,
            "now": target.name,
            "reason": reason,
            "next": "Answer the contact's last message now.",
        }
