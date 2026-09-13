from odoo.tests.common import TransactionCase


class TestGetAttachmentsByMimetype(TransactionCase):
    """_get_attachments_by_mimetype used to require an exact string match,
    which silently rejected any real-world mimetype carrying parameters
    (e.g. "audio/ogg; codecs=opus", exactly what Meta sends for every
    WhatsApp voice note) - the attachment would never be picked up for
    transcription, with no error and no log line.
    """

    def setUp(self):
        super().setUp()
        self.message = self.env["mail.message"].create(
            {
                "model": "res.partner",
                "res_id": self.env.user.partner_id.id,
                "body": "t",
            },
        )

    def _attach(self, mimetype):
        att = self.env["ir.attachment"].create(
            {
                "name": "a",
                "datas": b"ZGF0YQ==",
                "mimetype": mimetype,
                "res_model": "mail.message",
                "res_id": self.message.id,
            },
        )
        self.message.write({"attachment_ids": [(4, att.id)]})
        return att

    def test_mimetype_with_parameters_still_matches(self):
        att = self._attach("audio/ogg; codecs=opus")
        found = self.message._get_attachments_by_mimetype(("audio/ogg",))
        self.assertEqual(found, att)

    def test_bare_mimetype_still_matches(self):
        att = self._attach("audio/wav")
        found = self.message._get_attachments_by_mimetype(("audio/wav",))
        self.assertEqual(found, att)

    def test_non_matching_mimetype_still_excluded(self):
        self._attach("image/png")
        found = self.message._get_attachments_by_mimetype(("audio/ogg", "audio/wav"))
        self.assertFalse(found)

    def test_matching_is_case_insensitive_on_the_media_type(self):
        att = self._attach("AUDIO/OGG; codecs=opus")
        found = self.message._get_attachments_by_mimetype(("audio/ogg",))
        self.assertEqual(found, att)
