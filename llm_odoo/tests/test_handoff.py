from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLLMHandoff(TransactionCase):
    """Handoff policy tests; no provider or real-model call is involved."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        prompt = cls.env["llm.prompt"].create({
            "name": "handoff test prompt",
            "template": "Answer briefly.",
        })
        cls.owner = cls.env["llm.assistant"].create({
            "name": "Owner assistant", "code": "owner_test", "prompt_id": prompt.id,
        })
        cls.sales = cls.env["llm.assistant"].create({
            "name": "Sales assistant", "code": "sales_test", "prompt_id": prompt.id,
        })
        cls.other = cls.env["llm.assistant"].create({
            "name": "Other assistant", "code": "other_test", "prompt_id": prompt.id,
        })
        cls.provider = cls.env["llm.provider"].create({
            "name": "Handoff test provider", "service": "openai", "api_key": "not-used",
        })
        cls.model = cls.env["llm.model"].create({
            "name": "handoff-test-model", "provider_id": cls.provider.id,
            "model_use": "chat",
        })
        cls.owner.write({"provider_id": cls.provider.id, "model_id": cls.model.id})
        cls.sales.write({"provider_id": cls.provider.id, "model_id": cls.model.id})
        cls.other.write({"provider_id": cls.provider.id, "model_id": cls.model.id})
        cls.owner.write({"handoff_assistant_ids": [(4, cls.sales.id)]})
        cls.contact = cls.env["res.partner"].create({"name": "Handoff contact"})
        account = cls.env["whatsapp.account"].create({
            "name": "Handoff WABA", "waba_id": "handoff-test",
            "access_token": "not-used", "platform_company_id": cls.env.company.id,
        })
        cls.phone = cls.env["whatsapp.phone.number"].create({
            "account_id": account.id, "phone_number_id": "handoff-phone",
            "display_phone_number": "+221 70 000 00 00",
            "default_assistant_id": cls.owner.id,
            "sales_assistant_id": cls.sales.id,
        })
        cls.thread = cls.env["llm.thread"].create({
            "name": "handoff test thread", "assistant_id": cls.owner.id,
            "provider_id": cls.provider.id, "model_id": cls.model.id,
            "model": "res.partner", "res_id": cls.contact.id,
            "whatsapp_phone_number_id": cls.phone.id,
        })
        cls.user_message = cls.thread.message_post(
            body="I want to buy this.", llm_role="user",
        )

    def _call(self, assistant="sales_test"):
        return self.env["llm.handoff.tools"].with_context(
            message=self.user_message,
        ).llm_hand_off(assistant, "customer requested sales help")

    def test_allowed_target_switches_assistant_and_tools(self):
        result = self._call()
        self.assertTrue(result["success"], result)
        self.assertEqual(self.thread.assistant_id, self.sales)
        self.assertEqual(self.thread.tool_ids, self.sales.tool_ids)
        self.assertEqual(
            self.thread._prepare_chat_kwargs([], False)["tools"], self.sales.tool_ids,
        )

    def test_refused_target_and_self_target(self):
        self.assertFalse(self._call("other_test")["success"])
        self.assertFalse(self._call("owner_test")["success"])

    def test_handoff_only_once_for_the_same_user_turn(self):
        self.assertTrue(self._call()["success"])
        handoff_message = self.thread.message_post(
            body="handoff result", llm_role="tool",
            body_json={"tool_name": "llm_hand_off"},
        )
        self.user_message = self.user_message
        self.assertFalse(self._call()["success"])
        self.assertTrue(handoff_message)

    def test_new_user_turn_allows_a_new_handoff(self):
        self.assertTrue(self._call()["success"])
        self.thread.message_post(
            body="handoff result", llm_role="tool",
            body_json={"tool_name": "llm_hand_off"},
        )
        self.user_message = self.thread.message_post(
            body="Please continue with sales.", llm_role="user",
        )
        # The owner must be current for the allowlist check; this models the
        # handback path explicitly without invoking generation.
        self.thread.set_assistant(self.owner.id)
        self.assertTrue(self._call()["success"])
