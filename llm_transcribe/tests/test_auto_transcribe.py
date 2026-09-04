import base64
from unittest.mock import patch

from odoo import tools
from odoo.tests.common import TransactionCase

WAV = base64.b64encode(b"RIFF____WAVEfmt ").decode()


class TestAutoTranscribe(TransactionCase):
    def setUp(self):
        super().setUp()
        # Creating a transcription model dispatches the schema hooks, so pick a
        # service that actually implements them.
        Provider = self.env["llm.provider"]
        service = next(
            (
                code
                for code, _label in Provider._selection_service()
                if hasattr(Provider, f"{code}_should_generate_transcription_schema")
            ),
            None,
        )
        if not service:
            self.skipTest("no provider implements the transcription schema hooks")
        self.provider = self.env["llm.provider"].create(
            {"name": "Auto Transcribe Test", "service": service, "api_key": "k"},
        )
        self.chat_model = self.env["llm.model"].create(
            {
                "name": "chat-model",
                "provider_id": self.provider.id,
                "model_use": "chat",
            },
        )
        self.asr_model = self.env["llm.model"].create(
            {
                "name": "asr-model",
                "provider_id": self.provider.id,
                "model_use": "transcription",
            },
        )
        self.thread = self.env["llm.thread"].create(
            {
                "name": "Auto transcribe thread",
                "provider_id": self.provider.id,
                "model_id": self.chat_model.id,
            },
        )

    def _audio_attachment(self, name="note.wav"):
        return self.env["ir.attachment"].create(
            {"name": name, "datas": WAV, "mimetype": "audio/wav"},
        )

    def _post(self, body="", attachments=None, llm_role="user"):
        kwargs = {"body": body, "llm_role": llm_role}
        if attachments:
            kwargs["attachment_ids"] = attachments.ids
        return self.thread.message_post(**kwargs)

    def test_transcript_is_appended_to_user_message(self):
        att = self._audio_attachment()
        with patch.object(
            type(self.env["ir.attachment"]),
            "transcribe_attachments",
            return_value=[{"attachment_name": "note.wav", "transcript": "Jàmm rekk."}],
        ):
            message = self._post("listen to this", att)
        # Assert on the rendered text: Html fields escape plain str, which would
        # leave literal tags in the model's context.
        rendered = tools.html2plaintext(message.body)
        self.assertIn("Jàmm rekk.", rendered)
        self.assertIn("Audio transcript", rendered)
        self.assertIn("listen to this", rendered)
        self.assertNotIn("<p>", rendered)
        self.assertNotIn("&lt;", message.body)

    def test_transcript_html_is_escaped_not_injected(self):
        att = self._audio_attachment()
        with patch.object(
            type(self.env["ir.attachment"]),
            "transcribe_attachments",
            return_value=[
                {"attachment_name": "n.wav", "transcript": "<script>alert(1)</script>"}
            ],
        ):
            message = self._post("hi", att)
        self.assertNotIn("<script>", message.body)
        self.assertIn("alert(1)", tools.html2plaintext(message.body))

    def test_no_audio_leaves_body_untouched(self):
        with patch.object(
            type(self.env["ir.attachment"]), "transcribe_attachments"
        ) as transcribe:
            message = self._post("just text")
        transcribe.assert_not_called()
        self.assertNotIn("Audio transcript", message.body or "")

    def test_assistant_messages_are_not_transcribed(self):
        att = self._audio_attachment()
        with patch.object(
            type(self.env["ir.attachment"]), "transcribe_attachments"
        ) as transcribe:
            self._post("generated", att, llm_role="assistant")
        transcribe.assert_not_called()

    def test_missing_transcription_model_is_not_fatal(self):
        self.asr_model.active = False
        self.env["llm.model"].search([("model_use", "=", "transcription")]).write(
            {"active": False}
        )
        att = self._audio_attachment()
        message = self._post("hello", att)
        # The message must still post, just without a transcript.
        self.assertIn("hello", message.body)
        self.assertNotIn("Audio transcript", message.body)

    def test_transcription_failure_never_blocks_the_message(self):
        att = self._audio_attachment()
        with patch.object(
            type(self.env["ir.attachment"]),
            "transcribe_attachments",
            side_effect=RuntimeError("provider exploded"),
        ):
            message = self._post("hello", att)
        self.assertIn("hello", message.body)
        self.assertNotIn("Audio transcript", message.body)

    def test_per_attachment_error_is_reported_inline(self):
        att = self._audio_attachment()
        with patch.object(
            type(self.env["ir.attachment"]),
            "transcribe_attachments",
            return_value=[
                {"attachment_name": "note.wav", "error": "unsupported format"}
            ],
        ):
            message = self._post("hello", att)
        rendered = tools.html2plaintext(message.body)
        self.assertIn("transcription failed", rendered)
        self.assertIn("unsupported format", rendered)

    def test_default_transcription_model_is_preferred(self):
        other = self.env["llm.model"].create(
            {
                "name": "asr-default",
                "provider_id": self.provider.id,
                "model_use": "transcription",
                "default": True,
            },
        )
        self.assertEqual(self.thread._get_auto_transcription_model(), other)
