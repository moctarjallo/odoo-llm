import json
from typing import Any

from odoo import api, models
from odoo.exceptions import UserError


class LLMToolTranscribe(models.Model):
    _inherit = "llm.tool"

    @api.model
    def _get_available_implementations(self):
        implementations = super()._get_available_implementations()
        return implementations + [("odoo_transcribe", "Odoo Audio Transcriber")]

    def odoo_transcribe_execute(
        self, inputs: dict[str, Any], model_id: int = None
    ) -> dict[str, Any]:
        """Transcribe audio using structured inputs.

        ``model_id`` is optional: an assistant calling this tool has no way to
        know a valid transcription model id, so omitting it resolves the
        default (or any active) transcription model automatically instead of
        failing outright.
        """
        self.ensure_one()

        if isinstance(inputs, str):
            try:
                inputs = json.loads(inputs)
            except (ValueError, TypeError):
                pass

        if not isinstance(inputs, dict):
            raise UserError("inputs must be an object")

        model = self._odoo_transcribe_resolve_model(model_id)

        attachment_ids = inputs.get("attachment_ids") or []
        if isinstance(attachment_ids, str):
            try:
                attachment_ids = json.loads(attachment_ids)
            except (ValueError, TypeError):
                attachment_ids = [attachment_ids]
        if not isinstance(attachment_ids, list) or not attachment_ids:
            raise UserError("inputs.attachment_ids must be a non-empty list")

        prompt = (inputs.get("prompt") or "").strip() or None
        language = (inputs.get("language") or "").strip() or None

        results = self.env["ir.attachment"].transcribe_attachments(
            model=model,
            attachment_ids=attachment_ids,
            prompt=prompt,
            language=language,
        )

        tool_message = self.env.context.get("message")
        markdown_content = (
            tool_message.process_transcription_results(results)
            if tool_message
            else self.env["mail.message"].format_transcription_results(results)
        )

        output_data = {
            "provider": model.provider_id.service,
            "model_name": model.name,
            "inputs": inputs,
            "num_results": len(results),
        }

        return {
            "success": True,
            "output_data": output_data,
            "results": results,
            "markdown": markdown_content,
            "content_count": len(results),
        }

    def _odoo_transcribe_resolve_model(self, model_id):
        """Same preference order as llm.thread._get_auto_transcription_model:
        the default transcription model, else any active one."""
        if model_id:
            model = self.env["llm.model"].browse(int(model_id))
            if not model.exists():
                raise UserError(f"Model with ID {model_id} not found")
            if model.model_use != "transcription":
                raise UserError(f"Model '{model.name}' is not a transcription model")
            return model

        Model = self.env["llm.model"]
        domain = [("model_use", "=", "transcription"), ("active", "=", True)]
        model = Model.search(
            domain + [("default", "=", True)], limit=1
        ) or Model.search(domain, limit=1)
        if not model:
            raise UserError(
                "No transcription model is configured. Create one under "
                "LLM / Configuration / Models."
            )
        return model
