# -*- coding: utf-8 -*-
{
    "name": "LLM ↔ Odoo Bridge",
    "summary": "Channel-agnostic foundation linking Odoo business logic to LLM threads",
    "description": """
LLM ↔ Odoo Bridge (the "C" layer foundation)
============================================

Defines the channel-agnostic contract between Odoo business operations (M) and
the conversational AI substrate (llm.thread), without knowing about any specific
channel (WhatsApp, email, …).

On ``llm.thread``:
  * ``inject_event(body)``     — hand a backend business result to the AI as a
                                 synthetic user turn, then trigger generation.
  * ``_on_user_message(msg)``  — channel layers call this after each inbound turn;
                                 dispatches to ``_run_pipeline()`` when the
                                 thread's assistant has ``auto_pipeline`` set.
  * ``_run_pipeline()``        — no-op hook; business C-modules (crm_llm) override.
  * ``_queue_generation()``    — run a generation pass (sync by default; channel
                                 modules override to enqueue).
  * ``partner_id`` / ``_get_transcript()`` — convenience accessors.

On ``llm.assistant``:
  * ``auto_pipeline``          — gate for business-pipeline automation.
  * ``structured_chat()``      — one-shot, no-history, JSON-parsed decision call
                                 (the C layer's decision primitive).
""",
    "category": "Productivity, Discuss",
    "version": "18.0.1.0.0",
    "depends": [
        "llm_thread",
        "llm_assistant",
    ],
    "author": "Ordomatics",
    "license": "LGPL-3",
    "installable": True,
    "application": False,
    "auto_install": False,
}
