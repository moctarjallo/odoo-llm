from odoo.tests.common import TransactionCase


class TestGenerationMimetype(TransactionCase):
    """fal.ai returned no content type, so edited images were stored as
    application/octet-stream and Meta refused to send them (smartacus, 2026-09-15)."""

    def setUp(self):
        super().setUp()
        self.Message = type(self.env["mail.message"])

    def test_octet_stream_falls_back_to_the_extension(self):
        url_data = {
            "url": "https://v3b.fal.media/files/b/0aaa7836/lO6kn.png",
            "content_type": "application/octet-stream",
            "filename": "lO6kn.png",
        }
        self.assertEqual(self.Message._generation_mimetype(url_data), "image/png")

    def test_missing_type_uses_the_url(self):
        url_data = {"url": "https://cdn.example.com/song.mp3?sig=1"}
        self.assertEqual(self.Message._generation_mimetype(url_data), "audio/mpeg")

    def test_a_real_type_is_kept(self):
        url_data = {"url": "https://x/voice", "content_type": "audio/ogg; codecs=opus"}
        self.assertEqual(self.Message._generation_mimetype(url_data), "audio/ogg; codecs=opus")

    def test_unknown_extension_stays_octet_stream(self):
        url_data = {"url": "https://x/blob", "content_type": ""}
        self.assertEqual(
            self.Message._generation_mimetype(url_data), "application/octet-stream"
        )

    def test_attachment_gets_the_guessed_type(self):
        message = self.env["mail.message"].create({"body": "generation"})
        _markdown, attachments = message.process_generation_urls(
            [{"url": "https://v3b.fal.media/files/b/x/edit.png", "content_type": "application/octet-stream"}]
        )
        self.assertEqual(attachments[0].mimetype, "image/png")
