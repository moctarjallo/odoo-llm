"""model_use for a Fal model, from what it accepts and returns.

Fal's category alone is too coarse (object detection is filed as image-to-image),
so the OpenAPI schemas decide and the category only settles what they don't.
"""

import json
import re

_CATEGORY_MODEL_USE = {
    **dict.fromkeys(
        (
            "text-to-video", "image-to-video", "video-to-video", "audio-to-video",
            "text-to-audio", "audio-to-audio", "text-to-speech", "video-to-audio",
            "speech-to-speech", "text-to-3d", "image-to-3d", "3d-to-3d", "training",
        ),
        "generation",
    ),
    **dict.fromkeys(
        ("vision", "image-to-json", "text-to-json", "json", "audio-to-text",
         "video-to-text", "image-to-text"),
        "multimodal",
    ),
    "speech-to-text": "transcription",
    "text-to-image": "image_generation",
    "image-to-image": "image_generation",
    "llm": "chat",
}

_MESH = {"mesh", "glb", "gltf", "obj", "ply", "fbx", "usdz", "gaussian", "gaussians", "splat", "world", "model"}
_STEMS = {"bass", "drums", "vocals", "guitar", "piano", "other", "target", "residual", "stems"}
_DETECTIONS = {"results", "objects", "boxes", "bboxes", "points", "labels", "chunks", "detections", "polygons"}
_CLASSIFIER = {"nsfw_probability", "has_nsfw_concepts", "probability", "prediction", "metrics", "scores", "label", "embedding_b64"}
_TEXT = {"output", "text", "caption", "captions", "answer", "response", "content", "messages", "json", "data", "outputs", "prompt"}
_IMAGE_OUTPUT = re.compile(r"(image|images|output_image|image_url)")
_MEDIA_INPUT = re.compile(r"(image|images|video|videos|audio|media|file|files)(_data)?(_urls?)?$")
_WEIGHTS = re.compile(r"lora|safetensors|checkpoint|weights|config_file")


def _properties(schema):
    if not isinstance(schema, dict):
        return {}
    return {k.lower(): json.dumps(v).lower() for k, v in (schema.get("properties") or {}).items()}


def _is_file(spec):
    # A flag like has_speech names audio but isn't audio output.
    return any(t in spec for t in ("file", "url", "schemas/image", "schemas/video", "schemas/audio"))


def _tokens(name):
    return set(re.split(r"[_\-.]", name))


def derive_model_use(name, details):
    """Return (model_use, reason) for a Fal endpoint and its parsed details."""
    name = (name or "").lower()
    details = details or {}
    metadata = details.get("metadata") or {}
    category = (details.get("category") or metadata.get("category") or "").lower()

    if "embedding" in name:
        return "embedding", "embedding in name"
    if metadata.get("kind") == "training":
        return "generation", "trainer"

    outputs = _properties(details.get("output_schema"))
    inputs = _properties(details.get("input_schema"))
    names = set(outputs)

    if any(_WEIGHTS.search(n) for n in names):
        return "generation", "outputs weights"
    if names & {"lottie_file", "result_files", "speaker_embedding"} or names & _STEMS:
        return "generation", "outputs animation, files, stems or a voice"
    if any("video" in _tokens(n) and _is_file(outputs[n]) for n in names):
        return "generation", "outputs video"
    if any(_tokens(n) & {"audio", "speech", "voice"} and _is_file(outputs[n]) for n in names):
        return "generation", "outputs audio"
    if any(_tokens(n) & _MESH and _is_file(outputs[n]) for n in names):
        return "generation", "outputs 3d"

    image = [n for n in names if _IMAGE_OUTPUT.fullmatch(n)]
    if image and names & _DETECTIONS:
        return "multimodal", "outputs image and detections"
    if image:
        return "image_generation", "outputs image"
    if any("mask" in n or "depth" in n or "normal_map" in n for n in names):
        return "multimodal", "outputs masks or depth"
    if names & _CLASSIFIER:
        return "multimodal", "outputs scores or embeddings"

    media_in = [n for n in inputs if _MEDIA_INPUT.search(n)]
    audio_in = any("audio" in n for n in media_in)
    if names & {"words", "characters"} or (names & _TEXT and audio_in and category == "speech-to-text"):
        return "transcription", "audio in, text out"
    if names & _TEXT or names & _DETECTIONS:
        if media_in:
            return "multimodal", "media in, text out"
        return "chat", "text in, text out"

    if category in _CATEGORY_MODEL_USE:
        return _CATEGORY_MODEL_USE[category], f"category {category}"
    return "chat", "unrecognised"
