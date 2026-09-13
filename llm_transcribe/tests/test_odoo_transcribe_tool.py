from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestOdooTranscribeModelIdOptional(TransactionCase):
    """odoo_transcribe_execute's model_id used to be required, but an assistant
    calling this tool has no way to know a valid model id - it can only guess,
    and any wrong guess raised "Model with ID X not found" before the call ever
    reached a provider. Confirmed live: this is exactly what broke a real
    WhatsApp voice-note transcription attempt.
    """

    def setUp(self):
        super().setUp()
        self.tool = self.env.ref("llm_transcribe.llm_tool_odoo_transcribe")
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
            {"name": "Transcribe Tool Test", "service": service, "api_key": "k"},
        )

    def test_resolves_default_model_when_model_id_omitted(self):
        other = self.env["llm.model"].create(
            {
                "name": "not-default",
                "provider_id": self.provider.id,
                "model_use": "transcription",
            },
        )
        default = self.env["llm.model"].create(
            {
                "name": "the-default",
                "provider_id": self.provider.id,
                "model_use": "transcription",
                "default": True,
            },
        )
        resolved = self.tool._odoo_transcribe_resolve_model(None)
        self.assertEqual(resolved, default)
        self.assertNotEqual(resolved, other)

    def test_resolves_any_active_model_when_no_default_set(self):
        model = self.env["llm.model"].create(
            {
                "name": "only-one",
                "provider_id": self.provider.id,
                "model_use": "transcription",
            },
        )
        self.assertEqual(self.tool._odoo_transcribe_resolve_model(None), model)

    def test_raises_clearly_when_none_configured(self):
        self.env["llm.model"].search([("model_use", "=", "transcription")]).write(
            {"active": False},
        )
        with self.assertRaises(UserError):
            self.tool._odoo_transcribe_resolve_model(None)

    def test_explicit_model_id_still_honored(self):
        model = self.env["llm.model"].create(
            {
                "name": "explicit",
                "provider_id": self.provider.id,
                "model_use": "transcription",
            },
        )
        self.assertEqual(self.tool._odoo_transcribe_resolve_model(model.id), model)

    def test_wrong_model_use_still_rejected(self):
        chat_model = self.env["llm.model"].create(
            {"name": "chat", "provider_id": self.provider.id, "model_use": "chat"},
        )
        with self.assertRaises(UserError):
            self.tool._odoo_transcribe_resolve_model(chat_model.id)

    def test_execute_works_without_model_id(self):
        att = self.env["ir.attachment"].create(
            {"name": "n.wav", "datas": b"RIFF", "mimetype": "audio/wav"},
        )
        model = self.env["llm.model"].create(
            {
                "name": "auto-model",
                "provider_id": self.provider.id,
                "model_use": "transcription",
                "default": True,
            },
        )
        with patch.object(
            type(self.env["ir.attachment"]),
            "transcribe_attachments",
            return_value=[{"attachment_name": "n.wav", "transcript": "hello"}],
        ) as transcribe:
            result = self.tool.odoo_transcribe_execute({"attachment_ids": [att.id]})
        self.assertTrue(result["success"])
        transcribe.assert_called_once()
        _, kwargs = transcribe.call_args
        self.assertEqual(kwargs["model"], model)
