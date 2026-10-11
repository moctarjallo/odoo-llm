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

    transcription_model_id = fields.Many2one(
        "llm.model",
        string="Voice Note Model",
        domain=[("model_use", "=", "transcription")],
        ondelete="set null",
        help=(
            "Transcription model for this assistant's voice notes. Leave empty to "
            "use the default transcription model. Pick one that understands the "
            "languages this assistant's contacts speak."
        ),
    )
