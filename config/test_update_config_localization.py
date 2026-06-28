import importlib.util
import json
import pathlib
import tempfile
import unittest


SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / ".github" / "scripts" / "build_update_config.py"
spec = importlib.util.spec_from_file_location("build_update_config", SCRIPT_PATH)
build_update_config = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(build_update_config)


class UpdateConfigLocalizationTest(unittest.TestCase):
    def test_generates_locale_outputs_with_english_fallback_and_v2_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._write_minimal_source(root)

            legacy, localized, summary = build_update_config.compile_update_bundle(root)

            self.assertEqual(legacy["schema_version"], 2)
            self.assertIn("de", localized)
            self.assertEqual(localized["de"]["schema_version"], 3)
            self.assertEqual(localized["de"]["locale"], "de")
            self.assertEqual(
                localized["de"]["announcement"]["contents"],
                {"en": ["English summary"]},
            )
            self.assertEqual(summary["localized_outputs"], list(build_update_config.SUPPORTED_LOCALES))

    def test_source_locale_prefers_source_content_over_english_translation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._write_minimal_source(root)
            self._write_english_translation(root)

            _legacy, localized, _summary = build_update_config.compile_update_bundle(root)

            self.assertEqual(localized["zh-Hans"]["announcement"]["title"], "v1.0.0")
            self.assertEqual(
                localized["zh-Hans"]["announcement"]["contents"],
                {"zh-Hans": ["Chinese summary"]},
            )
            self.assertEqual(
                localized["zh-Hans"]["release_notes"][0]["items"][0]["contents"],
                {"zh-Hans": ["Chinese feature"]},
            )
            self.assertEqual(localized["en"]["announcement"]["title"], "Release Notes")

    def test_rejects_v1_manifest_for_localized_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._write_minimal_source(root, schema_version=1)

            with self.assertRaises(build_update_config.ConfigError):
                build_update_config.compile_update_bundle(root)

    def test_rejects_localized_file_with_localized_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._write_minimal_source(root)
            localized = root / "locales" / "en" / "announcements"
            localized.mkdir(parents=True)
            (localized / "20260511.json").write_text(
                json.dumps(
                    {
                        "id": "20260511",
                        "locale": "en",
                        "title": {"en": "Title"},
                        "summary": ["English summary"],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(build_update_config.ConfigError):
                build_update_config.compile_update_bundle(root)

    def _write_minimal_source(self, root: pathlib.Path, *, schema_version: int = 2) -> None:
        (root / "announcements").mkdir(parents=True)
        (root / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": schema_version,
                    "version_info": {"android": {"latest_version": "1.0.0"}},
                    "notice_enabled": False,
                    "notice": None,
                    "announcement_ids": ["20260511"],
                    "latest_announcement_id": "20260511",
                }
            ),
            encoding="utf-8",
        )
        (root / "announcements" / "20260511.json").write_text(
            json.dumps(
                {
                    "id": "20260511",
                    "version": "1.0.0",
                    "date": "2026-05-11",
                    "title": "v1.0.0",
                    "contents": {
                        "zh": ["Chinese summary"],
                        "en": ["English summary"],
                    },
                    "items": [
                        {
                            "category": "feature",
                            "contents": {
                                "zh": ["Chinese feature"],
                                "en": ["English feature"],
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def _write_english_translation(self, root: pathlib.Path) -> None:
        localized = root / "locales" / "en" / "announcements"
        localized.mkdir(parents=True)
        (localized / "20260511.json").write_text(
            json.dumps(
                {
                    "id": "20260511",
                    "locale": "en",
                    "title": "Release Notes",
                    "summary": ["Translated English summary"],
                    "items": [
                        {
                            "category": "feature",
                            "contents": ["Translated English feature"],
                        }
                    ],
                    "translation": {"status": "reviewed"},
                }
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
