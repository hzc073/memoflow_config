import importlib.util
import pathlib
import subprocess
import tempfile
import unittest


SERVER_PATH = pathlib.Path(__file__).resolve().parent / "server.py"
spec = importlib.util.spec_from_file_location("manager_server", SERVER_PATH)
manager_server = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(manager_server)


class GitCommitAnnouncementTest(unittest.TestCase):
    def test_discovers_tag_range_and_classifies_commits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            app_repo = root / "app"
            app_repo.mkdir()
            self._git(app_repo, "init")
            self._git(app_repo, "config", "user.email", "test@example.com")
            self._git(app_repo, "config", "user.name", "Test User")

            self._commit_file(app_repo, "app.txt", "base\n", "feat: initial base")
            self._git(app_repo, "tag", "v1.0.0")
            self._commit_file(app_repo, "app.txt", "base\nfix\n", "fix: repair sync issue")
            self._commit_file(app_repo, "readme.md", "docs\n", "docs: update release notes")

            repo = manager_server.ConfigRepository(root)
            ranges = repo.git_commit_range_options({"repoPath": str(app_repo)})
            commits = repo.git_commit_options({"repoPath": str(app_repo), "limit": "all"})

            self.assertEqual(ranges["repoPath"], str(app_repo.resolve()))
            self.assertEqual(ranges["options"][0]["fromRef"], "v1.0.0")
            self.assertEqual(ranges["options"][0]["toRef"], "HEAD")
            self.assertEqual(commits["commits"][0]["subject"], "docs: update release notes")
            self.assertEqual(commits["commits"][1]["subject"], "fix: repair sync issue")
            self.assertEqual(commits["limit"], 0)
            self.assertIn("hash", commits["commits"][0])

            result = repo.generate_announcement_items_from_commits(
                {
                    "repoPath": str(app_repo),
                    "fromRef": commits["commits"][2]["hash"],
                    "toRef": commits["commits"][0]["hash"],
                    "limit": ranges["options"][0]["limit"],
                }
            )

            by_category = {item["category"]: item["contents"] for item in result["items"]}
            self.assertEqual(result["count"], 2)
            self.assertEqual(by_category["fix"]["en"], ["repair sync issue"])
            self.assertEqual(by_category["improvement"]["en"], ["update release notes"])

    def _commit_file(self, repo: pathlib.Path, name: str, content: str, message: str) -> None:
        (repo / name).write_text(content, encoding="utf-8")
        self._git(repo, "add", name)
        self._git(repo, "commit", "-m", message)

    def _git(self, repo: pathlib.Path, *args: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            self.fail(completed.stderr or completed.stdout)
        return completed.stdout


if __name__ == "__main__":
    unittest.main()
