from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestFalAIProvider(TransactionCase):
    def setUp(self):
        super().setUp()
        self.provider = self.env["llm.provider"].create(
            {
                "name": "Test Fal.ai",
                "service": "fal_ai",
                "api_key": "test-key",
            }
        )

    def test_import_model_use_is_the_derived_capability(self):
        self.assertEqual(
            self.provider._determine_model_use("fal-ai/flux/dev", ["image_generation"]),
            "image_generation",
        )
        self.assertEqual(
            self.provider._determine_model_use("fal-ai/ltx-video", ["generation"]),
            "generation",
        )

    def test_unknown_capability_falls_back_to_base_rules(self):
        self.assertEqual(
            self.provider._determine_model_use("fal-ai/x", ["not-a-model-use"]), "chat"
        )

    def test_other_providers_keep_base_rules(self):
        other = self.env["llm.provider"].new({"name": "Other", "service": False})
        self.assertEqual(
            other._determine_model_use("some-image-model", ["image_generation"]), "chat"
        )

    def test_transcription_data_url_drops_mimetype_parameters(self):
        """WhatsApp voice notes are "audio/ogg; codecs=opus"; Fal rejected the
        parameterised data URL as "Unsupported data URL" (smartacus, 2026-09-13)."""
        model = self.env["llm.model"].new(
            {
                "name": "fal-ai/wizper",
                "details": {"input_schema": {"properties": {"audio_url": {}}}},
            }
        )
        inputs = self.provider._fal_ai_build_transcription_inputs(
            model, b"OggS", "voice.ogg", "audio/ogg; codecs=opus"
        )
        self.assertTrue(inputs["audio_url"].startswith("data:audio/ogg;base64,"))

    def test_parse_model_extracts_openapi_schemas(self):
        raw_model = {
            "endpoint_id": "fal-ai/flux/dev",
            "metadata": {
                "category": "text-to-image",
                "description": "Fast text-to-image generation",
            },
            "openapi": {
                "components": {
                    "schemas": {
                        "Input": {"type": "object", "properties": {"prompt": {"type": "string"}}},
                        "Output": {"type": "array", "items": {"type": "string"}},
                    }
                }
            },
        }

        parsed = self.provider._fal_ai_parse_model(raw_model)

        self.assertEqual(parsed["name"], "fal-ai/flux/dev")
        self.assertEqual(parsed["details"]["capabilities"], ["image_generation"])
        self.assertEqual(parsed["details"]["category"], "text-to-image")
        self.assertIn("input_schema", parsed["details"])
        self.assertIn("output_schema", parsed["details"])

    def test_parse_model_extracts_named_openapi_refs(self):
        raw_model = {
            "endpoint_id": "fal-ai/bytedance/seedance/v1/pro/image-to-video",
            "metadata": {
                "category": "image-to-video",
                "description": "Image to video",
            },
            "openapi": {
                "paths": {
                    "/model": {
                        "post": {
                            "requestBody": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "$ref": "#/components/schemas/SeedanceInput"
                                        }
                                    }
                                },
                                "required": True,
                            },
                            "responses": {
                                "200": {
                                    "content": {
                                        "application/json": {
                                            "schema": {
                                                "$ref": "#/components/schemas/QueueStatus"
                                            }
                                        }
                                    }
                                }
                            },
                        }
                    },
                    "/model/requests/{request_id}": {
                        "get": {
                            "responses": {
                                "200": {
                                    "content": {
                                        "application/json": {
                                            "schema": {
                                                "$ref": "#/components/schemas/SeedanceOutput"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    },
                },
                "components": {
                    "schemas": {
                        "QueueStatus": {"type": "object"},
                        "SeedanceInput": {
                            "type": "object",
                            "required": ["prompt", "image_url"],
                            "properties": {
                                "prompt": {"type": "string"},
                                "image_url": {"type": "string"},
                            },
                        },
                        "SeedanceOutput": {
                            "type": "object",
                            "properties": {"video": {"type": "object"}},
                        },
                    }
                },
            },
        }

        parsed = self.provider._fal_ai_parse_model(raw_model)

        input_schema = parsed["details"]["input_schema"]
        output_schema = parsed["details"]["output_schema"]
        self.assertEqual(input_schema["required"], ["prompt", "image_url"])
        self.assertIn("image_url", input_schema["properties"])
        self.assertIn("video", output_schema["properties"])

    def test_resolve_inputs_uses_openapi_schema_fallback(self):
        model = self.env["llm.model"].create({
            "name": "fal-ai/bytedance/seedance/v1/pro/image-to-video",
            "provider_id": self.provider.id,
            "model_use": "generation",
            "details": {
                "openapi": {
                    "paths": {
                        "/model": {
                            "post": {
                                "requestBody": {
                                    "content": {
                                        "application/json": {
                                            "schema": {
                                                "$ref": "#/components/schemas/SeedanceInput"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "components": {
                        "schemas": {
                            "SeedanceInput": {
                                "type": "object",
                                "required": ["prompt", "image_url"],
                                "properties": {
                                    "prompt": {"type": "string"},
                                    "image_url": {"type": "string"},
                                },
                            }
                        }
                    },
                }
            },
        })

        resolved = self.provider._fal_ai_resolve_inputs(
            {"image": "https://example.com/image.jpg", "prompt": "make it move"},
            model,
        )

        self.assertEqual(resolved["image_url"], "https://example.com/image.jpg")
        self.assertNotIn("image", resolved)

    def test_validate_inputs_fails_before_fal_api_when_prompt_missing(self):
        model = self.env["llm.model"].create({
            "name": "fal-ai/bytedance/seedance/v1/pro/image-to-video",
            "provider_id": self.provider.id,
            "model_use": "generation",
            "details": {
                "input_schema": {
                    "type": "object",
                    "required": ["prompt", "image_url"],
                    "properties": {
                        "prompt": {"type": "string"},
                        "image_url": {"type": "string"},
                    },
                }
            },
        })

        with self.assertRaisesRegex(UserError, "prompt"):
            self.provider._fal_ai_validate_inputs({"image_url": "x"}, model)

    def _edit_model(self, name, required, properties):
        return self.env["llm.model"].create({
            "name": name,
            "provider_id": self.provider.id,
            "model_use": "generation",
            "details": {
                "input_schema": {
                    "type": "object",
                    "required": required,
                    "properties": properties,
                }
            },
        })

    def test_several_images_fill_an_image_urls_model(self):
        # Photo plus the person to add, as asked on smartacus 2026-09-15.
        model = self._edit_model(
            "alibaba/qwen-image-3/edit",
            ["image_urls", "prompt"],
            {"image_urls": {"type": "array"}, "prompt": {"type": "string"}},
        )
        resolved = self.provider._fal_ai_resolve_inputs(
            {"image": ["https://x/photo.jpg", "https://x/elon.jpg"], "prompt": "add him"},
            model,
        )
        self.assertEqual(resolved["image_urls"], ["https://x/photo.jpg", "https://x/elon.jpg"])
        self.assertNotIn("image", resolved)
        self.assertEqual(resolved["prompt"], "add him")

    def test_single_image_and_reference_become_a_list(self):
        model = self._edit_model(
            "alibaba/qwen-image-3/edit",
            ["image_urls", "prompt"],
            {"image_urls": {"anyOf": [{"type": "array"}, {"type": "null"}]}, "prompt": {"type": "string"}},
        )
        resolved = self.provider._fal_ai_resolve_inputs(
            {"image": "https://x/photo.jpg", "reference_image": "https://x/elon.jpg", "prompt": "p"},
            model,
        )
        self.assertEqual(resolved["image_urls"], ["https://x/photo.jpg", "https://x/elon.jpg"])

    def test_prompt_fills_an_instruction_model(self):
        model = self._edit_model(
            "bria/fibo-edit/add_object_by_text",
            ["image_url", "instruction"],
            {"image_url": {"type": "string"}, "instruction": {"type": "string"}},
        )
        resolved = self.provider._fal_ai_resolve_inputs(
            {"image": "https://x/photo.jpg", "prompt": "add Elon Musk"}, model
        )
        self.assertEqual(resolved, {"image_url": "https://x/photo.jpg", "instruction": "add Elon Musk"})

    def test_declared_fields_are_never_moved(self):
        model = self._edit_model(
            "x/both",
            ["prompt"],
            {"prompt": {"type": "string"}, "instruction": {"type": "string"}},
        )
        resolved = self.provider._fal_ai_resolve_inputs({"prompt": "p"}, model)
        self.assertEqual(resolved, {"prompt": "p"})

    def test_missing_input_error_names_the_fields_the_model_takes(self):
        model = self._edit_model(
            "fal-ai/flux-pro/v1/fill",
            ["image_url", "mask_url", "prompt"],
            {"image_url": {}, "mask_url": {}, "prompt": {}, "seed": {}},
        )
        with self.assertRaisesRegex(UserError, "mask_url.*takes: image_url, mask_url, prompt, seed"):
            self.provider._fal_ai_validate_inputs({"image_url": "x", "prompt": "p"}, model)

    def test_input_schema_is_reachable_from_the_model(self):
        model = self._edit_model("x/m", ["prompt"], {"prompt": {}})
        self.assertEqual(model.generation_input_schema()["required"], ["prompt"])
