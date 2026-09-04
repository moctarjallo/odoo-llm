from odoo import fields, models


class LLMAssistant(models.Model):
    _inherit = "llm.assistant"

    transcription_language = fields.Selection(
        selection=[("wo", "Wolof"), ("fr", "French"), ("en", "English")],
        string="Voice Note Language",
        help=(
            "Language to render incoming voice notes in. Leave empty to keep the "
            "words as spoken. Set it to the language this assistant reasons best "
            "in - speech is translated on the way in, so the model never has to "
            "work in a language it handles poorly."
        ),
    )
