import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock


SERVER_PATH = pathlib.Path(__file__).resolve().parent / "server.py"
spec = importlib.util.spec_from_file_location("manager_server", SERVER_PATH)
manager_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(manager_server)


class FakeBuildRepository(manager_server.ConfigRepository):
    def __init__(self, repo_root: pathlib.Path) -> None:
        super().__init__(repo_root)
        self.build_roots: list[pathlib.Path] = []
        self.build_modes: list[bool] = []

    def _run_update_build(
        self,
        root: pathlib.Path,
        *,
        build: bool,
        output: pathlib.Path | None = None,
    ) -> dict:
        self.build_roots.append(pathlib.Path(root).resolve())
        self.build_modes.append(build)
        return {
            "ok": True,
            "returncode": 0,
            "stdout": "ok",
            "stderr": "",
            "command": "fake-build",
            "output": str(output or ""),
        }


class GuidedReleaseConfigManagerTest(unittest.TestCase):
    def test_normalizes_github_release_assets_for_dashboard(self) -> None:
        release = manager_server.normalize_github_release(
            {
                "id": 1,
                "tag_name": "v1.0.33",
                "name": "MemoFlow 1.0.33",
                "published_at": "2026-06-09T15:00:00Z",
                "assets": [
                    {
                        "id": 10,
                        "name": "MemoFlow_v1.0.33-full-arm64-v8a-release.apk",
                        "download_count": 12,
                        "browser_download_url": "https://example.test/app.apk",
                    },
                    {
                        "id": 11,
                        "name": "MemoFlow_v1.0.33_windows_x64_setup.exe",
                        "download_count": 7,
                        "browser_download_url": "https://example.test/app.exe",
                    },
                ],
            }
        )

        self.assertEqual(release["version"], "1.0.33")
        self.assertEqual(release["total_downloads"], 19)
        self.assertEqual(release["assets"][0]["platform"], "android")
        self.assertEqual(release["assets"][1]["platform"], "windows")

    def test_github_settings_read_environment_without_exposing_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = manager_server.ConfigRepository(pathlib.Path(tmp))
            with mock.patch.dict(
                os.environ,
                {
                    "MEMOFLOW_CONFIG_GITHUB_TOKEN": "secret-token",
                    "MEMOFLOW_CONFIG_GITHUB_REPO": "owner/app",
                    "MEMOFLOW_CONFIG_GITHUB_CACHE_TTL_SECONDS": "42",
                },
                clear=False,
            ):
                settings = repo.github_settings()

        self.assertEqual(settings["repo"], "owner/app")
        self.assertTrue(settings["token_configured"])
        self.assertEqual(settings["cache_ttl_seconds"], 42)
        self.assertNotIn("secret-token", json.dumps(settings))

    def test_release_groups_use_semver_sorting_and_surface_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._write_minimal_source(root)
            self._write_announcement(root, "20260109", "1.0.9", "v1.0.9")
            self._write_announcement(root, "20260110", "1.0.10", "v1.0.10")
            manifest = self._read_manifest(root)
            manifest["announcement_ids"] = ["20260109", "20260110"]
            manifest["latest_announcement_id"] = "20260110"
            manifest["updates"] = [
                {
                    "id": "update-android-full-1.0.10",
                    "status": "public",
                    "platform": "android",
                    "channel": "full",
                    "version": "1.0.10",
                    "download_url": "",
                }
            ]
            self._write_manifest(root, manifest)

            repo = manager_server.ConfigRepository(root)
            groups = repo.release_groups([])

        self.assertEqual([group["version"] for group in groups[:2]], ["1.0.10", "1.0.9"])
        self.assertTrue(any("缺少下载链接" in issue for issue in groups[0]["issues"]))

    def test_release_draft_preview_validates_temp_tree_without_writing_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._write_minimal_source(root)
            repo = FakeBuildRepository(root)

            result = repo.release_draft_preview(
                {
                    "announcement": {
                        "version": "1.0.34",
                        "release_tag": "v1.0.34",
                        "date": "2026-06-10",
                        "title": "Release",
                        "contents": {"zh": ["summary"]},
                        "items": [{"category": "improvement", "contents": {"zh": ["item"]}}],
                    },
                    "build": False,
                }
            )

            self.assertTrue(result["validation"]["ok"])
            self.assertFalse((root / "update" / "announcements" / result["draft"]["announcement_id"]).exists())
            self.assertNotEqual(repo.build_roots[0], (root / "update").resolve())

    def test_publish_release_draft_writes_local_files_and_optional_build_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self._write_minimal_source(root)
            repo = FakeBuildRepository(root)

            data = repo.publish_release_draft(
                {
                    "announcement": {
                        "version": "1.0.34",
                        "release_tag": "v1.0.34",
                        "date": "2026-06-10",
                        "title": "Release",
                        "contents": {"zh": ["summary"]},
                    },
                    "updates": [
                        {
                            "id": "update-android-full-1.0.34",
                            "status": "public",
                            "platform": "android",
                            "channel": "full",
                            "version": "1.0.34",
                            "download_url": "https://example.test/app.apk",
                        }
                    ],
                    "legacy_syncs": [{"id": "update-android-full-1.0.34", "platform": "android"}],
                    "build": True,
                }
            )

            saved_id = data["releaseDraftResult"]["draft"]["announcement_id"]
            manifest = self._read_manifest(root)
            self.assertIn(saved_id, manifest["announcement_ids"])
            self.assertEqual(manifest["latest_announcement_id"], saved_id)
            self.assertEqual(manifest["version_info"]["android"]["latest_version"], "1.0.34")
            self.assertEqual(manifest["updates"][0]["release_note_id"], saved_id)
            self.assertTrue((root / "update" / "announcements" / f"{saved_id}.json").exists())
            self.assertEqual(repo.build_modes, [False, False, True])

    def _write_minimal_source(self, root: pathlib.Path) -> None:
        (root / "update" / "announcements").mkdir(parents=True)
        (root / "update" / "donors.json").write_text("[]\n", encoding="utf-8")
        self._write_announcement(root, "20260101", "1.0.1", "v1.0.1")
        self._write_manifest(
            root,
            {
                "schema_version": 2,
                "version_info": {},
                "notice_enabled": False,
                "notice": None,
                "announcement_tag_index": {"v1.0.1": "20260101"},
                "announcement_ids": ["20260101"],
                "latest_announcement_id": "20260101",
                "updates": [],
                "notices": [],
            },
        )

    def _write_announcement(self, root: pathlib.Path, ann_id: str, version: str, tag: str) -> None:
        path = root / "update" / "announcements" / f"{ann_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "id": ann_id,
                    "version": version,
                    "release_tag": tag,
                    "date": "2026-01-01",
                    "title": "Release",
                    "contents": {"zh": ["summary"]},
                    "items": [],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    def _read_manifest(self, root: pathlib.Path) -> dict:
        return json.loads((root / "update" / "manifest.json").read_text(encoding="utf-8"))

    def _write_manifest(self, root: pathlib.Path, manifest: dict) -> None:
        (root / "update").mkdir(parents=True, exist_ok=True)
        (root / "update" / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
