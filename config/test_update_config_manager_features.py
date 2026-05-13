import base64
import importlib.util
import pathlib
import re
import tempfile
import unittest


SERVER_PATH = pathlib.Path(__file__).resolve().parent / "server.py"
spec = importlib.util.spec_from_file_location("manager_server", SERVER_PATH)
manager_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(manager_server)


class ManagerFeatureTest(unittest.TestCase):
    def test_ai_summary_is_limited_to_50_characters(self) -> None:
        class FakeRepository(manager_server.ConfigRepository):
            def load_ai_settings(self) -> dict[str, str]:
                return {
                    "api_key": "test-key",
                    "base_url": "https://example.test/v1",
                    "model": "test-model",
                }

            def _request_ai_summary(self, *, announcement: dict, settings: dict[str, str]) -> dict:
                return {
                    "summary": [
                        (
                            "\u8fd9\u662f\u4e00\u6bb5\u8d85\u8fc7\u4e94\u5341\u4e2a\u5b57"
                            "\u7684\u4e2d\u6587\u66f4\u65b0\u6458\u8981\uff0c"
                            "\u7528\u4e8e\u9a8c\u8bc1\u540e\u7aef\u4f1a\u5f3a\u5236"
                            "\u9650\u5236\u957f\u5ea6\u5e76\u8fd4\u56de\u5355\u6bb5\u6587\u672c"
                        )
                    ]
                }

        with tempfile.TemporaryDirectory() as tmp:
            repo = FakeRepository(pathlib.Path(tmp))
            result = repo.generate_announcement_summary_with_ai(
                {
                    "announcement": {
                        "id": "20260513",
                        "title": "v1.0.0",
                        "contents": {},
                        "items": [
                            {
                                "category": "feature",
                                "contents": {"zh": ["\u65b0\u589e AI \u6458\u8981"]},
                            }
                        ],
                    }
                }
            )

        self.assertEqual(result["limit"], 50)
        self.assertEqual(len(result["summary"]), 1)
        self.assertLessEqual(len(result["summary"][0]), 50)

    def test_upload_asset_auto_names_avatar_from_name_and_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = manager_server.ConfigRepository(pathlib.Path(tmp))
            result = repo.upload_asset(
                {
                    "filename": r"C:\fakepath\avatar.webp",
                    "path": r"C:\fakepath\avatar-source.webp",
                    "name": "** \u9752",
                    "donor_id": "qing",
                    "auto_name": True,
                    "data": base64.b64encode(b"webp-bytes").decode("ascii"),
                }
            )

            filename = result["filename"]
            self.assertRegex(filename, re.compile(r"^\d{14}_qing_avatar_source\.webp$"))
            self.assertTrue((pathlib.Path(tmp) / "update" / "assets" / filename).exists())
            self.assertEqual(
                result["url"],
                f"{manager_server.ASSET_PUBLIC_BASE_URL}{filename}",
            )


if __name__ == "__main__":
    unittest.main()
