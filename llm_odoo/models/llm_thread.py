# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class LlmThread(models.Model):
    """Channel-agnostic bridge between Odoo business logic and the LLM thread.

    All methods here are channel-independent. Channel modules (whatsapp_llm, …)
    override ``_queue_generation`` to enqueue work and feed inbound messages via
    ``_on_user_message``. Business C-modules (crm_llm, sale_llm, …) override
    ``_run_pipeline`` and call ``inject_event`` to report results back to the AI.
    """

    _inherit = "llm.thread"

    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        compute="_compute_partner_id",
        help="The contact this thread is about, when it is keyed on a partner.",
    )

    @api.depends("model", "res_id")
    def _compute_partner_id(self):
        for thread in self:
            if thread.model == "res.partner" and thread.res_id:
                thread.partner_id = self.env["res.partner"].browse(thread.res_id)
            else:
                thread.partner_id = self.env["res.partner"]

    # -------------------------------------------------------------------------
    # Event injection (M/C → conversational AI)
    # -------------------------------------------------------------------------

    def record_event(self, body):
        """Record a backend result in the AI context without generating.

        This is useful when a channel has already delivered a transactional
        notification directly and the assistant still needs the fact in its
        later transcript. It does not call an LLM or consume credits.
        """
        self.ensure_one()
        message = self.with_context(mail_create_nosubscribe=True).message_post(
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
            author_id=self.env.ref("base.user_root").partner_id.id,
        )
        message.sudo().write({"llm_role": "user"})
        return message

    def inject_event(self, body):
        """Hand a backend business result to the conversational AI.

        Posts ``body`` as a synthetic ``llm_role='user'`` turn (so only the AI
        sees it — it never appears as an outbound channel message), then triggers
        a generation pass so the assistant composes the customer-facing reply in
        its own voice.
        """
        message = self.record_event(body)
        self._queue_generation()
        return message

    def _llm_event_assistant(self):
        """Return an assistant to use before generating a backend event reply."""
        return self.env["llm.assistant"]

    def _handoff_target_allowed(self, target):
        """Channel hook for validating a handoff target beyond the allowlist."""
        return True

    def _queue_generation(self):
        """Run a generation pass. Synchronous by default; channel modules override
        to enqueue via queue_job (e.g. whatsapp channel)."""
        self.ensure_one()
        for _ in self.generate():
            pass

    # -------------------------------------------------------------------------
    # Inbound dispatch (V → C)
    # -------------------------------------------------------------------------

    def _on_user_message(self, message):
        """Called by the channel layer after each inbound user turn.

        Drives business-pipeline automation when the thread's assistant is
        configured for it. Channel-agnostic: the gate is the assistant flag,
        never a channel-specific field.
        """
        self.ensure_one()
        if self.assistant_id.auto_pipeline and self.partner_id:
            self._run_pipeline()

    def _run_pipeline(self):
        """No-op hook; business C-modules (crm_llm) override to run automation."""
        return

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_transcript(self, limit=20):
        """Recent conversation as plain text, newest ``limit`` user/assistant turns."""
        self.ensure_one()
        messages = self.message_ids.filtered(
            lambda m: m.llm_role in ("user", "assistant") and m.body
        ).sorted("id")[-limit:]
        lines = [
            f"{'Customer' if m.llm_role == 'user' else 'Agent'}: {m.body}"
            for m in messages
        ]
        return "\n".join(lines) if lines else "(no messages yet)"
