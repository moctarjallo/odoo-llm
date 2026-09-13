from odoo.tests.common import BaseCase

from odoo.addons.llm_fal_ai.models.fal_ai_model_use import derive_model_use

FILE = {"$ref": "#/components/schemas/File"}
IMAGE = {"$ref": "#/components/schemas/Image"}
STRING = {"type": "string"}


def _use(name="fal-ai/x", category="", kind=None, inputs=None, outputs=None):
    details = {
        "category": category,
        "metadata": {"kind": kind} if kind else {},
        "input_schema": {"type": "object", "properties": inputs or {}},
        "output_schema": {"type": "object", "properties": outputs or {}},
    }
    return derive_model_use(name, details)[0]


class TestDeriveModelUse(BaseCase):
    """Each case is a shape found checking the rule against 1515 smartacus models."""

    def test_image_output(self):
        self.assertEqual(_use(category="text-to-image", outputs={"images": {"type": "array"}}), "image_generation")

    def test_image_with_description_stays_image_generation(self):
        # Gemini image / Nano Banana return a description alongside the images.
        self.assertEqual(
            _use(category="text-to-image", outputs={"images": {"type": "array"}, "description": STRING}),
            "image_generation",
        )

    def test_detections_are_multimodal_despite_category(self):
        # Florence-2 object detection is filed as image-to-image.
        self.assertEqual(
            _use(category="image-to-image", outputs={"image": IMAGE, "results": {"$ref": "#/components/schemas/BoundingBoxes"}}),
            "multimodal",
        )

    def test_frame_interpolation_returns_video(self):
        # fal-ai/film and fal-ai/rife are filed as image-to-image.
        self.assertEqual(_use(category="image-to-image", outputs={"video": FILE}), "generation")

    def test_speech_output(self):
        self.assertEqual(_use(category="text-to-audio", outputs={"audio": FILE}), "generation")

    def test_trainer(self):
        self.assertEqual(_use(kind="training", outputs={"diffusers_lora_file": FILE}), "generation")

    def test_vision_model_takes_media_input(self):
        self.assertEqual(_use(category="vision", inputs={"image_url": STRING}, outputs={"output": STRING}), "multimodal")

    def test_batched_vision_input_name(self):
        self.assertEqual(_use(inputs={"images_data_url": STRING}, outputs={"outputs": {"type": "array"}}), "multimodal")

    def test_text_only_llm_is_chat(self):
        self.assertEqual(_use(category="llm", inputs={"prompt": STRING}, outputs={"output": STRING}), "chat")

    def test_depth_maps_are_multimodal(self):
        self.assertEqual(_use(category="image-to-image", outputs={"depth_map": IMAGE, "normal_map": IMAGE}), "multimodal")

    def test_forced_alignment_is_transcription(self):
        self.assertEqual(
            _use(category="speech-to-text", inputs={"audio_url": STRING}, outputs={"words": {"type": "array"}}),
            "transcription",
        )

    def test_embedding_router_by_name(self):
        self.assertEqual(_use(name="openrouter/router/openai/v1/embeddings", category="llm"), "embedding")

    def test_speech_flag_is_not_audio_output(self):
        # silero-vad reports has_speech; that is not a generated audio file.
        self.assertEqual(
            _use(category="audio-to-text", inputs={"audio_url": STRING}, outputs={"has_speech": {"type": "boolean"}}),
            "multimodal",
        )

    def test_unrecognised_output_falls_back_to_category(self):
        # Realtime endpoints return connection details, not media.
        self.assertEqual(_use(category="video-to-video", outputs={"sdp": STRING, "iceservers": {"type": "array"}}), "generation")
