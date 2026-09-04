import json
import logging

from markupsafe import Markup

from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.llm.models.mail_message import AUDIO_MIMETYPES
from odoo.addons.llm_assistant.utils import render_template

_logger = logging.getLogger(__name__)


class LLMThread(models.Model):
    _inherit = "llm.thread"

    model_id = fields.Many2one(
        "llm.model",
        string="Model",
        required=True,
        domain=(
            "[('provider_id', '=', provider_id), "
            "('model_use', 'in', ['chat', 'multimodal', "
            "'generation', 'image_generation', 'transcription'])]"
        ),
        ondelete="restrict",
    )

    def message_post(self, *, llm_role=None, **kwargs):
        """Transcribe audio on incoming user messages.

        Most chat models cannot hear, and nothing surfaces attachment ids into
        their context, so a voice note would otherwise be invisible to them.
        Folding the transcript into the body makes voice input work for every
        provider without any of them knowing about audio.
        """
        message = super().message_post(llm_role=llm_role, **kwargs)
        if llm_role == "user":
            self._auto_transcribe_attachments(message)
        return message

    def _auto_transcribe_attachments(self, message):
        """Append transcripts of any audio attachments to the message body.

        Never raises: a transcription failure must not stop the user's message
        from being posted.
        """
        self.ensure_one()
        try:
            attachments = message._get_attachments_by_mimetype(AUDIO_MIMETYPES)
            if not attachments:
                return
            model = self._get_auto_transcription_model()
            if not model:
                _logger.warning(
                    "Audio attached to thread %s but no transcription model is "
                    "configured; skipping auto-transcription.",
                    self.id,
                )
                return
            results = self.env["ir.attachment"].transcribe_attachments(
                model=model,
                attachment_ids=attachments.ids,
                target_language=self._get_auto_transcription_language(),
            )
            body = self._format_auto_transcripts(results)
            if body:
                # Html fields escape plain str in Odoo 18; Markup keeps the markup.
                message.body = Markup(message.body or "") + body
        except Exception:
            _logger.exception(
                "Auto-transcription failed for message %s; leaving it as posted.",
                message.id,
            )

    def _get_auto_transcription_language(self):
        """Language to render voice notes in, per the thread's assistant.

        Empty means keep the words as spoken.
        """
        assistant = getattr(self, "assistant_id", None)
        return assistant.transcription_language if assistant else None

    def _get_auto_transcription_model(self):
        """The transcription model to use: the default one, else any active one."""
        Model = self.env["llm.model"]
        domain = [("model_use", "=", "transcription"), ("active", "=", True)]
        return Model.search(domain + [("default", "=", True)], limit=1) or Model.search(
            domain, limit=1
        )

    def _format_auto_transcripts(self, results):
        parts = []
        for result in results:
            label = result.get("attachment_name") or "Audio"
            if result.get("error"):
                parts.append(
                    Markup("<p><em>[Audio transcription failed for %s: %s]</em></p>")
                    % (label, result["error"])
                )
                continue
            transcript = (result.get("transcript") or "").strip()
            if transcript:
                parts.append(
                    Markup("<p><em>[Audio transcript - %s]</em><br/>%s</p>")
                    % (label, transcript)
                )
        return Markup("").join(parts)

    def get_transcription_input_schema(self):
        """Get input schema for transcription forms."""
        self.ensure_one()

        if (
            hasattr(self, "assistant_id")
            and self.assistant_id
            and self.assistant_id.prompt_id
        ):
            prompt_schema = self._ensure_dict(
                self.assistant_id.prompt_id.input_schema_json
            )
            if prompt_schema and prompt_schema.get("properties"):
                return prompt_schema

        if self.prompt_id and hasattr(self.prompt_id, "input_schema_json"):
            prompt_schema = self._ensure_dict(self.prompt_id.input_schema_json)
            if prompt_schema and prompt_schema.get("properties"):
                return prompt_schema

        if self.model_id and self.model_id.details:
            return self._ensure_dict(self.model_id.details.get("input_schema", {}))

        return {}

    def _ensure_dict(self, value):
        """Convert value to dict if it's a JSON string."""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return {}
        return {}

    def get_transcription_form_defaults(self):
        """Get default values for transcription form from context."""
        self.ensure_one()
        context = self.get_context()
        schema = self.get_transcription_input_schema()
        defaults = dict(context)

        if schema.get("properties"):
            for prop_name, prop_def in schema["properties"].items():
                if prop_name not in defaults and "default" in prop_def:
                    defaults[prop_name] = prop_def["default"]

            defaults = {
                key: value
                for key, value in defaults.items()
                if key in schema["properties"] and value is not None
            }

        return defaults

    def get_transcription_form_config(self):
        """Get form configuration for transcription."""
        self.ensure_one()
        return {
            "input_schema": self.get_transcription_input_schema(),
            "form_defaults": self.get_transcription_form_defaults(),
        }

    def prepare_transcription_inputs(self, inputs, attachment_ids=None):
        """Prepare final inputs for transcription."""
        self.ensure_one()

        context = self.get_context()
        merged_inputs = {**context, **inputs}

        if attachment_ids and not merged_inputs.get("attachment_ids"):
            merged_inputs["attachment_ids"] = attachment_ids.ids

        if not self.prompt_id:
            return merged_inputs

        try:
            rendered = render_template(self.prompt_id.template, merged_inputs)
            final_inputs = json.loads(rendered)
            if attachment_ids and not final_inputs.get("attachment_ids"):
                final_inputs["attachment_ids"] = attachment_ids.ids
            return final_inputs
        except Exception as exc:
            _logger.error("Error rendering transcription prompt: %s", exc)
            return merged_inputs

    def _transcribe_response(self, message):
        """Handle a user message with transcription data in body_json."""
        self.ensure_one()

        final_inputs = self.prepare_transcription_inputs(
            message.body_json or {}, attachment_ids=message.attachment_ids
        )
        attachment_ids = final_inputs.get("attachment_ids") or []
        if not attachment_ids:
            raise UserError("No audio attachments were provided for transcription.")

        results = self.env["ir.attachment"].transcribe_attachments(
            model=self.model_id,
            attachment_ids=attachment_ids,
            prompt=(final_inputs.get("prompt") or "").strip() or None,
            language=(final_inputs.get("language") or "").strip() or None,
        )

        output_data = {
            "provider": self.model_id.provider_id.service,
            "model_name": self.model_id.name,
            "inputs": final_inputs,
            "num_results": len(results),
            "results": results,
        }

        transcription_message = self.message_post(
            body="",
            llm_role="assistant",
            body_json=output_data,
        )
        markdown_content = transcription_message.process_transcription_results(results)
        html_content = self._process_llm_body(markdown_content)
        transcription_message.write({"body": html_content})

        yield {
            "type": "message_create",
            "message": transcription_message.to_store_format(),
        }

        return transcription_message
