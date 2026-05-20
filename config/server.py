#!/usr/bin/env python3
"""Local MemoFlow config manager.

This server is intentionally small and local-only. It serves the static
manager UI and exposes fixed JSON APIs for editing split update config files.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import mimetypes
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib import error as urlerror
from urllib import request as urlrequest


HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_BODY_BYTES = 25 * 1024 * 1024
ANNOUNCEMENT_SUMMARY_LIMIT = 50
ASSET_PUBLIC_BASE_URL = "https://juanzeng.hzc073.com/memoflow/assets/"
SAFE_ASSET_SUFFIXES = {
    ".avif",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".svg",
    ".webp",
}
COMMIT_CATEGORY_ORDER = ("feature", "fix", "improvement")
FEATURE_COMMIT_TYPES = {"feat", "feature", "add", "added"}
FIX_COMMIT_TYPES = {"fix", "bug", "bugfix", "hotfix"}
IMPROVEMENT_COMMIT_TYPES = {
    "build",
    "chore",
    "ci",
    "docs",
    "perf",
    "refactor",
    "style",
    "test",
    "tests",
    "improve",
    "improvement",
}
CONVENTIONAL_COMMIT_RE = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\([^)]+\))?!?\s*[:：]\s*(?P<subject>.+)$")
VERSION_ONLY_COMMIT_RE = re.compile(r"^v?\d+(?:\.\d+){1,3}(?:[-+][\w.-]+)?$")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
SUPPORTED_LOCALES = ("zh-Hans", "zh-Hant-TW", "en", "ja", "de", "pt-BR", "ko")
SOURCE_LOCALE = "zh-Hans"
FALLBACK_LOCALE = "en"
TRANSLATION_STATUSES = {"ai_draft", "needs_review", "reviewed", "stale"}
LOCALIZED_DELIVERY_FIELDS = {
    "status",
    "priority",
    "severity",
    "publish_at",
    "publishAt",
    "expire_at",
    "expireAt",
    "audience",
    "platform",
    "platforms",
    "channel",
    "channels",
    "display",
    "dismiss_policy",
    "dismissPolicy",
}


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _is_relative_to(path: pathlib.Path, parent: pathlib.Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _string(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value).strip()


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_id(value: Any, *, where: str = "id") -> str:
    text = _string(value)
    if text.isdigit():
        return text
    raise ApiError(f"Invalid numeric announcement id in {where}: {value!r}")


def _normalize_lang_map(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, list[str]] = {}
    for raw_key, raw_value in value.items():
        key = _string(raw_key).lower().replace("_", "-")
        if not key:
            continue
        key = key.split("-")[0]
        values: list[str] = []
        if isinstance(raw_value, str):
            if raw_value.strip():
                values = [raw_value.strip()]
        elif isinstance(raw_value, list):
            values = [_string(item) for item in raw_value if _string(item)]
        if values:
            out[key] = values
    return out


def _normalize_locale_tag(value: Any) -> str:
    text = _string(value).replace("_", "-").lower()
    if text in {"zh", "zh-cn", "zh-sg", "zh-hans"}:
        return "zh-Hans"
    if text in {"zh-tw", "zh-hk", "zh-mo", "zh-hant", "zh-hant-tw"}:
        return "zh-Hant-TW"
    if text in {"en", "en-us", "en-gb"}:
        return "en"
    if text == "ja":
        return "ja"
    if text == "de":
        return "de"
    if text in {"pt", "pt-br"}:
        return "pt-BR"
    if text == "ko":
        return "ko"
    return ""


def _translation_status(value: Any) -> str:
    status = _string(value).lower()
    return status if status in TRANSLATION_STATUSES else "needs_review"


def _read_lines(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [_string(item) for item in value if _string(item)]
    return []


def _localized_values(value: Any, locale: str, *, fallback_locale: str = FALLBACK_LOCALE) -> list[str]:
    if not isinstance(value, dict):
        return _read_lines(value)
    normalized = _normalize_locale_tag(locale)
    fallback = _normalize_locale_tag(fallback_locale)
    by_locale: dict[str, list[str]] = {}
    for key, raw in value.items():
        canonical = _normalize_locale_tag(key)
        if not canonical and _string(key).lower().startswith("zh"):
            canonical = "zh-Hans"
        values = _read_lines(raw)
        if canonical and values and canonical not in by_locale:
            by_locale[canonical] = values
    if normalized and normalized in by_locale:
        return by_locale[normalized]
    if fallback and fallback in by_locale:
        return by_locale[fallback]
    return []


def _summary_text(value: Any) -> str:
    if isinstance(value, dict):
        values = _localized_values(value, SOURCE_LOCALE, fallback_locale=SOURCE_LOCALE)
    else:
        values = _read_lines(value)
    text = "；".join(values)
    return re.sub(r"\s+", " ", text).strip()


def _limit_summary_text(value: Any, *, limit: int = ANNOUNCEMENT_SUMMARY_LIMIT) -> str:
    text = _summary_text(value)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip(" ,，。.!！?？、；;：:")


def _ai_summary_lines(raw: dict[str, Any]) -> list[str]:
    summary = raw.get("summary")
    if summary is None:
        summary = raw.get("contents")
    text = _limit_summary_text(summary)
    return [text] if text else []


def _announcement_source_hash(announcement: dict[str, Any], source_locale: str = SOURCE_LOCALE) -> str:
    payload = {
        "title": _string(announcement.get("title")),
        "summary": _localized_values(
            announcement.get("contents"),
            source_locale,
            fallback_locale=source_locale,
        ),
        "items": [
            {
                "category": _string(item.get("category")) if isinstance(item, dict) else "",
                "contents": _localized_values(
                    item.get("contents") if isinstance(item, dict) else None,
                    source_locale,
                    fallback_locale=source_locale,
                ),
            }
            for item in _list(announcement.get("items"))
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_datetime(value: Any) -> dt.datetime | None:
    text = _string(value)
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _is_http_url(value: Any) -> bool:
    text = _string(value)
    return text.startswith("http://") or text.startswith("https://")


def _safe_git_ref(value: Any) -> str:
    text = _string(value)
    if any(ch in text for ch in "\r\n\0"):
        raise ApiError(f"Invalid git ref: {value!r}")
    return text


def _strip_commit_prefix(text: str, prefix: str) -> str:
    rest = text[len(prefix) :].strip()
    return rest.lstrip(":：-— ").strip() or text.strip()


def _classify_commit_subject(subject: str) -> tuple[str, str]:
    text = " ".join(subject.strip().split())
    match = CONVENTIONAL_COMMIT_RE.match(text)
    if match:
        commit_type = match.group("type").lower()
        cleaned = match.group("subject").strip()
        if commit_type in FEATURE_COMMIT_TYPES:
            return "feature", cleaned
        if commit_type in FIX_COMMIT_TYPES:
            return "fix", cleaned
        if commit_type in IMPROVEMENT_COMMIT_TYPES:
            return "improvement", cleaned

    lowered = text.lower()
    if lowered.startswith(("merge ", "revert ")) or VERSION_ONLY_COMMIT_RE.fullmatch(lowered):
        return "", text
    if text.startswith(("新增", "增加", "添加")):
        return "feature", _strip_commit_prefix(text, text[:2])
    if text.startswith(("修复", "修正")):
        return "fix", _strip_commit_prefix(text, text[:2])
    if text.startswith(("优化", "改进", "调整", "重构")):
        return "improvement", _strip_commit_prefix(text, text[:2])
    return "improvement", text


def _commit_text_language(text: str) -> str:
    return "zh" if CJK_RE.search(text) else "en"


def _has_content(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_has_content(item) for item in value)
    if isinstance(value, dict):
        return any(_has_content(item) for item in value.values())
    return False


def _has_english(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return _has_content(value.get("en") or value.get("en-US") or value.get("en_us"))


class ConfigRepository:
    def __init__(self, repo_root: pathlib.Path) -> None:
        self.repo_root = repo_root.resolve()
        self.config_root = (self.repo_root / "config").resolve()
        self.update_root = (self.repo_root / "update").resolve()
        self.announcements_root = (self.update_root / "announcements").resolve()
        self.locales_root = (self.update_root / "locales").resolve()
        self.assets_root = (self.update_root / "assets").resolve()
        self.dist_latest = (self.repo_root / "dist" / "update" / "latest.json").resolve()

    @property
    def manifest_path(self) -> pathlib.Path:
        return self.update_root / "manifest.json"

    @property
    def donors_path(self) -> pathlib.Path:
        return self.update_root / "donors.json"

    @property
    def ai_settings_path(self) -> pathlib.Path:
        return self.config_root / "ai.local.json"

    def relative_path(self, path: pathlib.Path) -> str:
        try:
            return path.resolve().relative_to(self.repo_root).as_posix()
        except ValueError:
            return str(path)

    def _assert_inside(self, path: pathlib.Path, parent: pathlib.Path) -> pathlib.Path:
        resolved = path.resolve()
        if not _is_relative_to(resolved, parent.resolve()):
            raise ApiError(f"Path is outside allowed root: {path}", HTTPStatus.FORBIDDEN)
        return resolved

    def _assert_write_allowed(self, path: pathlib.Path) -> pathlib.Path:
        resolved = path.resolve()
        if resolved == self.manifest_path.resolve() or resolved == self.donors_path.resolve():
            return resolved
        if _is_relative_to(resolved, self.announcements_root):
            if resolved.suffix.lower() == ".json":
                return resolved
        if _is_relative_to(resolved, self.locales_root):
            if resolved.suffix.lower() == ".json":
                return resolved
        if _is_relative_to(resolved, self.assets_root):
            return resolved
        if resolved == self.dist_latest:
            return resolved
        raise ApiError(f"Write path is not allowed: {path}", HTTPStatus.FORBIDDEN)

    def read_json_object(self, path: pathlib.Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ApiError(f"Missing file: {path}", HTTPStatus.NOT_FOUND) from exc
        except json.JSONDecodeError as exc:
            raise ApiError(f"Invalid JSON in {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ApiError(f"JSON object required in {path}")
        return data

    def read_json_list(self, path: pathlib.Path) -> list[Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ApiError(f"Missing file: {path}", HTTPStatus.NOT_FOUND) from exc
        except json.JSONDecodeError as exc:
            raise ApiError(f"Invalid JSON in {path}: {exc}") from exc
        if not isinstance(data, list):
            raise ApiError(f"JSON array required in {path}")
        return data

    def write_json(self, path: pathlib.Path, data: Any) -> None:
        target = self._assert_write_allowed(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        encoded = _json_dumps(data)
        json.loads(encoded)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=str(target.parent),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as tmp:
                tmp.write(encoded)
            os.replace(tmp_name, target)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def load_manifest(self) -> dict[str, Any]:
        return self.read_json_object(self.manifest_path)

    def load_donors(self) -> list[Any]:
        if not self.donors_path.exists():
            return []
        return self.read_json_list(self.donors_path)

    def announcement_path(self, announcement_id: str) -> pathlib.Path:
        normalized = _normalize_id(announcement_id, where="announcement id")
        return self.announcements_root / f"{normalized}.json"

    def load_announcement(self, announcement_id: str) -> dict[str, Any]:
        path = self.announcement_path(announcement_id)
        data = self.read_json_object(path)
        file_id = _normalize_id(data.get("id"), where=str(path))
        if file_id != announcement_id:
            raise ApiError(f"Announcement id mismatch in {path}: expected {announcement_id}, got {file_id}")
        return data

    def announcement_ids(self, manifest: dict[str, Any]) -> list[str]:
        ids = []
        for raw in _list(manifest.get("announcement_ids")):
            ids.append(_normalize_id(raw, where="manifest.announcement_ids"))
        if len(set(ids)) != len(ids):
            raise ApiError("manifest.announcement_ids contains duplicates")
        return ids

    def load_announcements(self, manifest: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for announcement_id in self.announcement_ids(manifest):
            item = self.load_announcement(announcement_id)
            out.append(item)
        return out

    def load_announcement_directory(self) -> list[dict[str, Any]]:
        if not self.announcements_root.exists():
            return []
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for path in sorted(self.announcements_root.glob("*.json")):
            data = self.read_json_object(path)
            ann_id = _normalize_id(data.get("id"), where=str(path))
            expected_name = f"{ann_id}.json"
            if path.name != expected_name:
                raise ApiError(f"Announcement filename mismatch: expected {expected_name}, got {path.name}")
            if ann_id in seen:
                raise ApiError(f"Duplicate announcement id in directory: {ann_id}")
            seen.add(ann_id)
            out.append(data)
        return out

    def history_sorted(self, announcements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            announcements,
            key=lambda item: int(_normalize_id(item.get("id"), where="announcement.id")),
            reverse=True,
        )

    def current_announcement(self, manifest: dict[str, Any]) -> dict[str, Any] | None:
        latest = _string(manifest.get("latest_announcement_id"))
        if not latest:
            return None
        return self.load_announcement(_normalize_id(latest, where="latest_announcement_id"))

    def donor_references(self, announcements: list[dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
        refs: dict[str, list[dict[str, str]]] = {}
        for announcement in announcements:
            ann_id = _string(announcement.get("id"))
            for donor_id in _list(announcement.get("new_donor_ids")):
                donor_key = _string(donor_id)
                if not donor_key:
                    continue
                refs.setdefault(donor_key, []).append(
                    {
                        "announcement_id": ann_id,
                        "version": _string(announcement.get("version")),
                        "title": _string(announcement.get("title")),
                    }
                )
        return refs

    def localized_diagnostics(
        self,
        manifest: dict[str, Any],
        announcements: list[dict[str, Any]],
    ) -> dict[str, list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        by_id = {_string(item.get("id")): item for item in announcements}
        referenced_ids = set(by_id)
        if not self.locales_root.exists():
            return {"errors": errors, "warnings": warnings}
        for locale in SUPPORTED_LOCALES:
            ann_dir = self.locales_root / locale / "announcements"
            if not ann_dir.exists():
                continue
            for path in sorted(ann_dir.glob("*.json")):
                try:
                    data = self.read_json_object(path)
                    ann_id = _normalize_id(data.get("id"), where=str(path))
                except ApiError as exc:
                    errors.append(str(exc))
                    continue
                if ann_id not in referenced_ids:
                    errors.append(f"{path} is not referenced by manifest.announcement_ids.")
                declared_locale = _normalize_locale_tag(data.get("locale"))
                if declared_locale != locale:
                    errors.append(f"{path} locale must be {locale}.")
                for field in LOCALIZED_DELIVERY_FIELDS:
                    if field in data:
                        errors.append(f"{path} must not define delivery field {field}.")
                for index, item in enumerate(_list(data.get("items"))):
                    if not isinstance(item, dict):
                        continue
                    for field in LOCALIZED_DELIVERY_FIELDS:
                        if field in item:
                            errors.append(f"{path}.items[{index}] must not define delivery field {field}.")
                translation = _dict(data.get("translation"))
                status = _string(translation.get("status")).lower()
                if status in {"ai_draft", "draft", "stale", "needs_review", "unreviewed"}:
                    errors.append(f"{path} translation status is {status}; review before publish.")
                source_hash = _string(translation.get("source_hash"))
                if source_hash and ann_id in by_id:
                    source_locale = _normalize_locale_tag(translation.get("source_locale")) or SOURCE_LOCALE
                    current_hash = _announcement_source_hash(by_id[ann_id], source_locale)
                    if source_hash != current_hash:
                        errors.append(f"{path} translation source hash is stale.")
        return {"errors": errors, "warnings": warnings}

    def generated_summary(self) -> dict[str, Any]:
        if not self.dist_latest.exists():
            return {"exists": False, "path": str(self.dist_latest)}
        stat = self.dist_latest.stat()
        summary: dict[str, Any] = {
            "exists": True,
            "path": str(self.dist_latest),
            "size": stat.st_size,
            "modified": dt.datetime.fromtimestamp(stat.st_mtime, tz=dt.timezone.utc).isoformat(),
        }
        try:
            data = json.loads(self.dist_latest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            summary["error"] = str(exc)
            return summary
        if isinstance(data, dict):
            localized_outputs = [
                path.name
                for path in sorted(self.dist_latest.parent.glob("latest.*.json"))
                if path.name != "latest.json"
            ]
            summary.update(
                {
                    "schema_version": data.get("schema_version"),
                    "has_notices": isinstance(data.get("notices"), list) and bool(data.get("notices")),
                    "has_updates": isinstance(data.get("updates"), list) and bool(data.get("updates")),
                    "release_notes_count": len(data.get("release_notes")) if isinstance(data.get("release_notes"), list) else 0,
                    "donors_count": len(data.get("donors")) if isinstance(data.get("donors"), list) else 0,
                    "localized_outputs": localized_outputs,
                }
            )
        return summary

    def localized_announcement_path(self, locale: str, announcement_id: str) -> pathlib.Path:
        normalized_locale = _normalize_locale_tag(locale)
        if normalized_locale not in SUPPORTED_LOCALES:
            raise ApiError(f"Unsupported locale: {locale!r}")
        ann_id = _normalize_id(announcement_id, where="announcement id")
        return self.locales_root / normalized_locale / "announcements" / f"{ann_id}.json"

    def load_localized_announcement(self, locale: str, announcement_id: str) -> dict[str, Any] | None:
        path = self.localized_announcement_path(locale, announcement_id)
        if not path.exists():
            return None
        return self.read_json_object(path)

    def localized_status_for_announcement(self, announcement: dict[str, Any]) -> dict[str, Any]:
        ann_id = _normalize_id(announcement.get("id"), where="announcement.id")
        source_hash = _announcement_source_hash(announcement, SOURCE_LOCALE)
        locales: dict[str, dict[str, Any]] = {}
        for locale in SUPPORTED_LOCALES:
            if locale == SOURCE_LOCALE:
                locales[locale] = {
                    "exists": True,
                    "source": True,
                    "status": "source",
                    "stale": False,
                    "path": self.relative_path(self.announcement_path(ann_id)),
                }
                continue
            path = self.localized_announcement_path(locale, ann_id)
            data = self.read_json_object(path) if path.exists() else None
            translation = _dict(data.get("translation")) if data else {}
            stored_hash = _string(translation.get("source_hash"))
            status = _translation_status(translation.get("status")) if data else "missing"
            stale = bool(data and stored_hash and stored_hash != source_hash)
            if stale and status == "reviewed":
                status = "stale"
            locales[locale] = {
                "exists": data is not None,
                "source": False,
                "status": status,
                "stale": stale,
                "summary_count": len(_read_lines(data.get("summary") or data.get("contents"))) if data else 0,
                "item_count": len(_list(data.get("items"))) if data else 0,
                "path": self.relative_path(path),
            }
        return {
            "id": ann_id,
            "version": _string(announcement.get("version")),
            "title": _string(announcement.get("title")),
            "source_hash": source_hash,
            "locales": locales,
        }

    def localized_status(self, announcements: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "source_locale": SOURCE_LOCALE,
            "fallback_locale": FALLBACK_LOCALE,
            "supported_locales": list(SUPPORTED_LOCALES),
            "announcements": {
                _string(item.get("id")): self.localized_status_for_announcement(item)
                for item in announcements
                if _string(item.get("id"))
            },
        }

    def localized_template(self, announcement: dict[str, Any], locale: str) -> dict[str, Any]:
        ann_id = _normalize_id(announcement.get("id"), where="announcement.id")
        normalized_locale = _normalize_locale_tag(locale)
        source_hash = _announcement_source_hash(announcement, SOURCE_LOCALE)
        return {
            "id": ann_id,
            "locale": normalized_locale,
            "title": "",
            "summary": [],
            "items": [
                {
                    "category": _string(item.get("category")) or "improvement",
                    "contents": [],
                }
                for item in _list(announcement.get("items"))
                if isinstance(item, dict)
            ],
            "translation": {
                "source_locale": SOURCE_LOCALE,
                "source_hash": source_hash,
                "status": "needs_review",
            },
        }

    def localized_editor_payload(self, announcement_id: str, locale: str) -> dict[str, Any]:
        ann_id = _normalize_id(announcement_id, where="announcement id")
        normalized_locale = _normalize_locale_tag(locale)
        if normalized_locale not in SUPPORTED_LOCALES or normalized_locale == SOURCE_LOCALE:
            raise ApiError(f"Unsupported target locale: {locale!r}")
        announcement = self.load_announcement(ann_id)
        path = self.localized_announcement_path(normalized_locale, ann_id)
        existing = self.load_localized_announcement(normalized_locale, ann_id)
        source_hash = _announcement_source_hash(announcement, SOURCE_LOCALE)
        data = existing or self.localized_template(announcement, normalized_locale)
        source_items = []
        for item in _list(announcement.get("items")):
            if not isinstance(item, dict):
                continue
            source_items.append(
                {
                    "category": _string(item.get("category")) or "improvement",
                    "contents": _localized_values(
                        item.get("contents"),
                        SOURCE_LOCALE,
                        fallback_locale=SOURCE_LOCALE,
                    ),
                }
            )
        translation = _dict(data.get("translation"))
        return {
            "exists": existing is not None,
            "path": self.relative_path(path),
            "source_hash": source_hash,
            "source": {
                "id": ann_id,
                "title": _string(announcement.get("title")),
                "summary": _localized_values(
                    announcement.get("contents"),
                    SOURCE_LOCALE,
                    fallback_locale=SOURCE_LOCALE,
                ),
                "items": source_items,
            },
            "announcement": data,
            "status": _translation_status(translation.get("status")),
            "stale": bool(_string(translation.get("source_hash")) and _string(translation.get("source_hash")) != source_hash),
        }

    def save_localized_announcement(self, payload: dict[str, Any]) -> dict[str, Any]:
        ann_id = _normalize_id(payload.get("announcement_id"), where="announcement id")
        locale = _normalize_locale_tag(payload.get("locale"))
        if locale not in SUPPORTED_LOCALES or locale == SOURCE_LOCALE:
            raise ApiError(f"Unsupported target locale: {payload.get('locale')!r}")
        announcement = self.load_announcement(ann_id)
        source_hash = _announcement_source_hash(announcement, SOURCE_LOCALE)
        raw = _dict(payload.get("announcement"))
        translation = _dict(raw.get("translation"))
        status = _translation_status(payload.get("status") or translation.get("status"))
        localized = normalize_localized_announcement_for_save(
            raw,
            announcement_id=ann_id,
            locale=locale,
            source_hash=source_hash,
            status=status,
        )
        self.write_json(self.localized_announcement_path(locale, ann_id), localized)
        data = self.load_all()
        data["localizedEditor"] = self.localized_editor_payload(ann_id, locale)
        return data

    def delete_localized_announcement(self, payload: dict[str, Any]) -> dict[str, Any]:
        ann_id = _normalize_id(payload.get("announcement_id"), where="announcement id")
        locale = _normalize_locale_tag(payload.get("locale"))
        if locale not in SUPPORTED_LOCALES or locale == SOURCE_LOCALE:
            raise ApiError(f"Unsupported target locale: {payload.get('locale')!r}")
        target = self._assert_write_allowed(self.localized_announcement_path(locale, ann_id))
        if target.exists():
            target.unlink()
        return self.load_all()

    def default_git_repo_path(self) -> pathlib.Path:
        candidates = [
            self.repo_root.parent / "memos",
            self.repo_root,
        ]
        for candidate in candidates:
            if (candidate / ".git").exists():
                return candidate.resolve()
        return self.repo_root

    def resolve_git_repo_path(self, value: Any) -> pathlib.Path:
        text = _string(value)
        path = pathlib.Path(text) if text else self.default_git_repo_path()
        if not path.is_absolute():
            path = self.repo_root / path
        path = path.resolve()
        if not path.exists() or not path.is_dir():
            raise ApiError(f"Git repository path does not exist: {path}")
        top = self.run_git(path, ["rev-parse", "--show-toplevel"]).strip()
        if not top:
            raise ApiError(f"Not a git repository: {path}")
        return pathlib.Path(top).resolve()

    def run_git(self, repo_path: pathlib.Path, args: list[str]) -> str:
        try:
            completed = subprocess.run(
                ["git", "-C", str(repo_path), *args],
                cwd=str(self.repo_root),
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            raise ApiError(f"Unable to run git: {exc}") from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
            raise ApiError(detail)
        return completed.stdout

    def latest_git_tag(self, repo_path: pathlib.Path) -> str:
        try:
            return self.run_git(repo_path, ["describe", "--tags", "--abbrev=0"]).strip()
        except ApiError:
            return ""

    def recent_git_tags(self, repo_path: pathlib.Path, limit: int = 12) -> list[dict[str, str]]:
        limit = max(1, min(limit, 50))
        raw = self.run_git(
            repo_path,
            [
                "for-each-ref",
                f"--count={limit}",
                "--sort=-v:refname",
                "--format=%(refname:short)",
                "refs/tags",
            ],
        )
        tags: list[dict[str, str]] = []
        for line in raw.splitlines():
            name = _string(line)
            if not name:
                continue
            tags.append(
                {
                    "name": name,
                    "date": "",
                }
            )
        return tags

    def git_commit_range_options(self, payload: dict[str, Any]) -> dict[str, Any]:
        repo_path = self.resolve_git_repo_path(payload.get("repoPath") or payload.get("repo_path"))
        try:
            tag_limit = int(payload.get("tagLimit") or payload.get("tag_limit") or 12)
        except (TypeError, ValueError):
            tag_limit = 12
        tags = self.recent_git_tags(repo_path, tag_limit)
        seen: set[str] = set()
        options: list[dict[str, Any]] = []

        def add_option(
            *,
            label: str,
            from_ref: str,
            to_ref: str,
            limit: int,
            kind: str,
            description: str = "",
        ) -> None:
            safe_from = _safe_git_ref(from_ref)
            safe_to = _safe_git_ref(to_ref) or "HEAD"
            revision = f"{safe_from}..{safe_to}" if safe_from else safe_to
            normalized_limit = max(1, min(int(limit or 80), 300))
            value = revision if safe_from else f"{revision}#last-{normalized_limit}"
            if value in seen:
                return
            seen.add(value)
            options.append(
                {
                    "value": value,
                    "label": label,
                    "fromRef": safe_from,
                    "toRef": safe_to,
                    "limit": normalized_limit,
                    "range": revision,
                    "kind": kind,
                    "description": description,
                }
            )

        latest_tag = tags[0]["name"] if tags else self.latest_git_tag(repo_path)
        if latest_tag:
            add_option(
                label=f"{latest_tag} -> HEAD",
                from_ref=latest_tag,
                to_ref="HEAD",
                limit=80,
                kind="latest_to_head",
                description="最新标签之后的提交，适合准备下一版公告。",
            )

        add_option(
            label="最近 20 次提交",
            from_ref="",
            to_ref="HEAD",
            limit=20,
            kind="recent_commits",
            description="不依赖标签，直接读取 HEAD 之前的最近提交。",
        )
        add_option(
            label="最近 50 次提交",
            from_ref="",
            to_ref="HEAD",
            limit=50,
            kind="recent_commits",
            description="范围较宽，适合标签缺失或批量整理。",
        )

        for index in range(len(tags) - 1):
            current = tags[index]["name"]
            previous = tags[index + 1]["name"]
            add_option(
                label=f"{previous} -> {current}",
                from_ref=previous,
                to_ref=current,
                limit=120,
                kind="tag_pair",
                description="两个相邻标签之间的提交，适合回溯某个已发布版本。",
            )

        return {
            "repoPath": str(repo_path),
            "tags": tags,
            "defaultValue": options[0]["value"] if options else "",
            "options": options,
        }

    def git_commit_options(self, payload: dict[str, Any]) -> dict[str, Any]:
        repo_path = self.resolve_git_repo_path(payload.get("repoPath") or payload.get("repo_path"))
        raw_limit = _string(payload.get("limit"))
        try:
            limit = 0 if raw_limit.lower() == "all" else int(raw_limit or 0)
        except (TypeError, ValueError):
            limit = 0
        if limit > 0:
            limit = max(1, min(limit, 5000))
        log_args = [
            "log",
            "--date=short",
            "--pretty=format:%H%x1f%h%x1f%s%x1f%ad%x1f%D",
        ]
        if limit > 0:
            log_args.insert(1, f"--max-count={limit}")
        log_args.append("HEAD")
        raw = self.run_git(
            repo_path,
            log_args,
        )
        commits: list[dict[str, str]] = []
        for line in raw.splitlines():
            parts = line.split("\x1f")
            if len(parts) != 5:
                continue
            full_hash, short_hash, subject, date_label, refs = parts
            commits.append(
                {
                    "hash": full_hash,
                    "short": short_hash,
                    "subject": subject,
                    "date": date_label,
                    "refs": refs,
                }
            )
        return {
            "repoPath": str(repo_path),
            "limit": limit,
            "commits": commits,
        }

    def git_defaults(self) -> dict[str, str]:
        repo_path = self.default_git_repo_path()
        return {
            "repoPath": str(repo_path),
            "fromRef": self.latest_git_tag(repo_path),
            "toRef": "HEAD",
        }

    def generate_announcement_items_from_commits(self, payload: dict[str, Any]) -> dict[str, Any]:
        repo_path = self.resolve_git_repo_path(payload.get("repoPath") or payload.get("repo_path"))
        from_ref = _safe_git_ref(payload.get("fromRef") or payload.get("from_ref"))
        if not from_ref:
            from_ref = self.latest_git_tag(repo_path)
        to_ref = _safe_git_ref(payload.get("toRef") or payload.get("to_ref")) or "HEAD"
        try:
            limit = int(payload.get("limit") or 80)
        except (TypeError, ValueError):
            limit = 80
        limit = max(1, min(limit, 300))

        revision = f"{from_ref}..{to_ref}" if from_ref else to_ref
        raw = self.run_git(
            repo_path,
            [
                "log",
                "--no-merges",
                f"--max-count={limit}",
                "--date=short",
                "--pretty=format:%H%x1f%h%x1f%s%x1f%ad",
                revision,
            ],
        )
        grouped: dict[str, dict[str, list[str]]] = {
            category: {"zh": [], "en": []} for category in COMMIT_CATEGORY_ORDER
        }
        commits: list[dict[str, str]] = []
        seen_lines: set[tuple[str, str]] = set()
        for line in raw.splitlines():
            parts = line.split("\x1f")
            if len(parts) != 4:
                continue
            full_hash, short_hash, subject, date_label = parts
            category, text = _classify_commit_subject(subject)
            if not category or not text:
                continue
            lang = "zh" if _commit_text_language(subject) == "zh" else _commit_text_language(text)
            key = (category, text)
            if key not in seen_lines:
                grouped[category][lang].append(text)
                seen_lines.add(key)
            commits.append(
                {
                    "hash": full_hash,
                    "short": short_hash,
                    "subject": subject,
                    "text": text,
                    "category": category,
                    "language": lang,
                    "date": date_label,
                }
            )

        items: list[dict[str, Any]] = []
        for category in COMMIT_CATEGORY_ORDER:
            contents = {
                lang: values
                for lang, values in grouped[category].items()
                if values
            }
            if contents:
                items.append({"category": category, "contents": contents})
        return {
            "repoPath": str(repo_path),
            "fromRef": from_ref,
            "toRef": to_ref,
            "range": revision,
            "limit": limit,
            "count": len(commits),
            "items": items,
            "commits": commits,
        }

    def load_ai_settings(self) -> dict[str, str]:
        local: dict[str, Any] = {}
        if self.ai_settings_path.exists():
            local = self.read_json_object(self.ai_settings_path)
        api_key = os.environ.get("MEMOFLOW_CONFIG_AI_API_KEY") or _string(local.get("api_key"))
        base_url = (
            os.environ.get("MEMOFLOW_CONFIG_AI_BASE_URL")
            or _string(local.get("base_url"))
            or "https://api.openai.com/v1"
        )
        model = os.environ.get("MEMOFLOW_CONFIG_AI_MODEL") or _string(local.get("model")) or "gpt-4.1-mini"
        return {"api_key": api_key, "base_url": base_url, "model": model}

    def ai_settings_summary(self) -> dict[str, Any]:
        local: dict[str, Any] = {}
        if self.ai_settings_path.exists():
            local = self.read_json_object(self.ai_settings_path)
        settings = self.load_ai_settings()
        return {
            "configured": bool(settings["api_key"]),
            "base_url": settings["base_url"],
            "model": settings["model"],
            "api_key_source": "env"
            if os.environ.get("MEMOFLOW_CONFIG_AI_API_KEY")
            else ("local" if _string(local.get("api_key")) else ""),
            "base_url_source": "env"
            if os.environ.get("MEMOFLOW_CONFIG_AI_BASE_URL")
            else ("local" if _string(local.get("base_url")) else "default"),
            "model_source": "env"
            if os.environ.get("MEMOFLOW_CONFIG_AI_MODEL")
            else ("local" if _string(local.get("model")) else "default"),
            "settings_path": self.relative_path(self.ai_settings_path),
        }

    def save_ai_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        local: dict[str, Any] = {}
        if self.ai_settings_path.exists():
            local = self.read_json_object(self.ai_settings_path)
        if "base_url" in payload:
            base_url = _string(payload.get("base_url"))
            if base_url:
                local["base_url"] = base_url
            else:
                local.pop("base_url", None)
        if "model" in payload:
            model = _string(payload.get("model"))
            if model:
                local["model"] = model
            else:
                local.pop("model", None)
        if payload.get("clear_api_key"):
            local.pop("api_key", None)
        else:
            api_key = _string(payload.get("api_key"))
            if api_key:
                local["api_key"] = api_key
        self.ai_settings_path.parent.mkdir(parents=True, exist_ok=True)
        encoded = _json_dumps(local)
        json.loads(encoded)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.ai_settings_path.name}.",
            suffix=".tmp",
            dir=str(self.ai_settings_path.parent),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as tmp:
                tmp.write(encoded)
            os.replace(tmp_name, self.ai_settings_path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        return self.load_all()

    def generate_announcement_summary_with_ai(self, payload: dict[str, Any]) -> dict[str, Any]:
        announcement = normalize_announcement(_dict(payload.get("announcement")))
        settings = self.load_ai_settings()
        if not settings["api_key"]:
            raise ApiError(
                "Missing AI settings. Set MEMOFLOW_CONFIG_AI_API_KEY or config/ai.local.json.",
                HTTPStatus.PRECONDITION_REQUIRED,
            )
        generated = self._request_ai_summary(announcement=announcement, settings=settings)
        summary = _ai_summary_lines(generated)
        if not summary:
            raise ApiError("AI summary response did not contain a usable summary.")
        return {
            "summary": summary,
            "limit": ANNOUNCEMENT_SUMMARY_LIMIT,
        }

    def _request_ai_summary(
        self,
        *,
        announcement: dict[str, Any],
        settings: dict[str, str],
    ) -> dict[str, Any]:
        base_url = settings["base_url"].rstrip("/")
        endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        source_payload = {
            "id": announcement.get("id"),
            "title": announcement.get("title"),
            "version": announcement.get("version"),
            "date": announcement.get("date"),
            "existing_summary": _localized_values(
                announcement.get("contents"),
                SOURCE_LOCALE,
                fallback_locale=SOURCE_LOCALE,
            ),
            "items": [
                {
                    "category": _string(item.get("category")),
                    "contents": _localized_values(
                        item.get("contents"),
                        SOURCE_LOCALE,
                        fallback_locale=SOURCE_LOCALE,
                    ),
                }
                for item in _list(announcement.get("items"))
                if isinstance(item, dict)
            ],
        }
        request_body = {
            "model": settings["model"],
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You write concise Simplified Chinese app update summaries. "
                        "Return strict JSON only: {\"summary\":[\"...\"]}. "
                        f"Write exactly one sentence and keep it within {ANNOUNCEMENT_SUMMARY_LIMIT} Chinese characters."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "source_locale": SOURCE_LOCALE,
                            "limit": ANNOUNCEMENT_SUMMARY_LIMIT,
                            "announcement": source_payload,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        data = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
        request = urlrequest.Request(
            endpoint,
            data=data,
            headers={
                "Authorization": f"Bearer {settings['api_key']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlrequest.urlopen(request, timeout=60) as response:
                response_body = response.read().decode("utf-8")
        except (OSError, urlerror.URLError) as exc:
            raise ApiError(f"AI summary request failed: {exc}") from exc
        try:
            decoded = json.loads(response_body)
            content = decoded["choices"][0]["message"]["content"]
            return _parse_ai_json_content(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ApiError("AI summary response did not contain valid JSON content.") from exc

    def translate_announcement_with_ai(self, payload: dict[str, Any]) -> dict[str, Any]:
        announcement = normalize_announcement(_dict(payload.get("announcement")))
        ann_id = _normalize_id(announcement.get("id"), where="announcement.id")
        target_locales = [
            locale
            for locale in (_normalize_locale_tag(item) for item in _list(payload.get("target_locales")))
            if locale in SUPPORTED_LOCALES and locale != SOURCE_LOCALE
        ]
        if not target_locales:
            target_locales = ["zh-Hant-TW", "en", "ja", "de", "pt-BR", "ko"]
        source_hash = _announcement_source_hash(announcement, SOURCE_LOCALE)
        settings = self.load_ai_settings()
        if not settings["api_key"]:
            raise ApiError(
                "Missing AI settings. Set MEMOFLOW_CONFIG_AI_API_KEY or config/ai.local.json.",
                HTTPStatus.PRECONDITION_REQUIRED,
            )

        overwrite = bool(payload.get("overwrite"))
        created: list[dict[str, str]] = []
        skipped: list[dict[str, str]] = []
        for locale in target_locales:
            existing = self.load_localized_announcement(locale, ann_id)
            if existing is not None and not overwrite:
                translation = _dict(existing.get("translation"))
                existing_hash = _string(translation.get("source_hash"))
                status = _translation_status(translation.get("status"))
                stale = existing_hash and existing_hash != source_hash
                if status == "reviewed" and not stale:
                    skipped.append({"locale": locale, "reason": "reviewed_current"})
                    continue
                if status not in {"stale", "needs_review", "ai_draft"} and not stale:
                    skipped.append({"locale": locale, "reason": "existing"})
                    continue
            translated = self._request_ai_translation(
                announcement=announcement,
                target_locale=locale,
                settings=settings,
            )
            localized = normalize_localized_announcement(
                translated,
                announcement_id=ann_id,
                locale=locale,
                source_hash=source_hash,
            )
            target = self.localized_announcement_path(locale, ann_id)
            self.write_json(target, localized)
            created.append({"locale": locale, "path": str(target)})
        data = self.load_all()
        data["aiTranslation"] = {
            "created": created,
            "skipped": skipped,
            "source_hash": source_hash,
        }
        return data

    def _request_ai_translation(
        self,
        *,
        announcement: dict[str, Any],
        target_locale: str,
        settings: dict[str, str],
    ) -> dict[str, Any]:
        base_url = settings["base_url"].rstrip("/")
        endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        source_payload = {
            "id": announcement.get("id"),
            "title": announcement.get("title"),
            "summary": _localized_values(
                announcement.get("contents"),
                SOURCE_LOCALE,
                fallback_locale=SOURCE_LOCALE,
            ),
            "items": [
                {
                    "category": _string(item.get("category")),
                    "contents": _localized_values(
                        item.get("contents"),
                        SOURCE_LOCALE,
                        fallback_locale=SOURCE_LOCALE,
                    ),
                }
                for item in _list(announcement.get("items"))
                if isinstance(item, dict)
            ],
        }
        request_body = {
            "model": settings["model"],
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You translate app release notes. Return strict JSON only with "
                        "keys title, summary, and items. Preserve category keys and item counts."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "target_locale": target_locale,
                            "source_locale": SOURCE_LOCALE,
                            "announcement": source_payload,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        data = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
        request = urlrequest.Request(
            endpoint,
            data=data,
            headers={
                "Authorization": f"Bearer {settings['api_key']}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlrequest.urlopen(request, timeout=60) as response:
                response_body = response.read().decode("utf-8")
        except (OSError, urlerror.URLError) as exc:
            raise ApiError(f"AI translation request failed: {exc}") from exc
        try:
            decoded = json.loads(response_body)
            content = decoded["choices"][0]["message"]["content"]
            return _parse_ai_json_content(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ApiError("AI translation response did not contain valid JSON content.") from exc

    def load_all(self) -> dict[str, Any]:
        manifest = self.load_manifest()
        donors = self.load_donors()
        referenced_announcements = self.load_announcements(manifest)
        directory_announcements = self.load_announcement_directory()
        current = self.current_announcement(manifest)
        diagnostics = validate_v3(manifest)
        localized_diagnostics = self.localized_diagnostics(manifest, referenced_announcements)
        diagnostics = {
            "errors": [*diagnostics["errors"], *localized_diagnostics["errors"]],
            "warnings": [*diagnostics["warnings"], *localized_diagnostics["warnings"]],
        }
        return {
            "repoRoot": str(self.repo_root),
            "manifest": manifest,
            "donors": donors,
            "announcements": directory_announcements,
            "referencedAnnouncements": referenced_announcements,
            "history": self.history_sorted(directory_announcements),
            "currentAnnouncement": current,
            "donorReferences": self.donor_references(directory_announcements),
            "generated": self.generated_summary(),
            "diagnostics": diagnostics,
            "gitDefaults": self.git_defaults(),
            "aiSettings": self.ai_settings_summary(),
            "localized": self.localized_status(directory_announcements),
        }

    def save_announcement(self, payload: dict[str, Any]) -> dict[str, Any]:
        announcement = normalize_announcement(_dict(payload.get("announcement")))
        manifest = self.load_manifest()
        requested = _string(announcement.get("id"))
        ann_id = requested if requested else self.generate_announcement_id(announcement)
        ann_id = _normalize_id(ann_id, where="announcement.id")
        announcement["id"] = ann_id
        self._index_announcement_in_manifest(manifest, announcement)
        self.write_json(self.announcement_path(ann_id), announcement)
        self.write_json(self.manifest_path, manifest)
        data = self.load_all()
        data["savedAnnouncementId"] = ann_id
        return data

    def _index_announcement_in_manifest(
        self,
        manifest: dict[str, Any],
        announcement: dict[str, Any],
    ) -> None:
        ann_id = _normalize_id(announcement.get("id"), where="announcement.id")
        ids = self.announcement_ids(manifest)
        if ann_id not in ids:
            ids.append(ann_id)
            manifest["announcement_ids"] = ids
        release_tag = _string(announcement.get("release_tag"))
        if release_tag:
            if not release_tag.startswith("v"):
                release_tag = f"v{release_tag}"
                announcement["release_tag"] = release_tag
            tag_index = manifest.get("announcement_tag_index")
            if not isinstance(tag_index, dict):
                tag_index = {}
            tag_index[release_tag] = ann_id
            manifest["announcement_tag_index"] = tag_index

    def create_announcement(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.save_announcement(payload)

    def set_latest_announcement(self, payload: dict[str, Any]) -> dict[str, Any]:
        ann_id = _normalize_id(payload.get("id"), where="announcement.id")
        announcement = normalize_announcement(self.load_announcement(ann_id))
        manifest = self.load_manifest()
        self._index_announcement_in_manifest(manifest, announcement)
        manifest["latest_announcement_id"] = ann_id
        self.write_json(self.manifest_path, manifest)
        return self.load_all()

    def delete_announcement(self, payload: dict[str, Any]) -> dict[str, Any]:
        ann_id = _normalize_id(payload.get("id"), where="announcement.id")
        manifest = self.load_manifest()
        ids = self.announcement_ids(manifest)
        if ann_id not in ids:
            raise ApiError(f"Announcement id is not referenced by manifest.announcement_ids: {ann_id}")
        if len(ids) <= 1:
            raise ApiError("Cannot delete the only announcement.")

        remaining = [item for item in ids if item != ann_id]
        manifest["announcement_ids"] = remaining

        if _string(manifest.get("latest_announcement_id")) == ann_id:
            manifest["latest_announcement_id"] = max(remaining, key=lambda item: int(item))

        tag_index = manifest.get("announcement_tag_index")
        if isinstance(tag_index, dict):
            manifest["announcement_tag_index"] = {
                key: value for key, value in tag_index.items() if _string(value) != ann_id
            }

        target = self._assert_write_allowed(self.announcement_path(ann_id))
        self.write_json(self.manifest_path, manifest)
        if target.exists():
            target.unlink()
        return self.load_all()

    def generate_announcement_id(self, announcement: dict[str, Any]) -> str:
        now = dt.datetime.now(dt.timezone.utc)
        base = now.strftime("%Y%m%d%H%M%S")
        seed = "|".join(
            [
                _string(announcement.get("release_tag")),
                _string(announcement.get("version")),
                _string(announcement.get("title")),
                now.isoformat(),
            ]
        )
        suffix = int(hashlib.sha1(seed.encode("utf-8")).hexdigest()[:6], 16) % 900 + 100
        candidate = f"{base}{suffix}"
        while self.announcement_path(candidate).exists():
            suffix = suffix + 1 if suffix < 999 else 100
            candidate = f"{base}{suffix}"
        return candidate

    def save_notices(self, payload: dict[str, Any]) -> dict[str, Any]:
        manifest = self.load_manifest()
        notices = [normalize_notice(item) for item in _list(payload.get("notices")) if isinstance(item, dict)]
        manifest["notices"] = notices
        legacy_notice_id = _string(payload.get("legacy_notice_id"))
        legacy_notice_enabled = payload.get("legacy_notice_enabled")
        if legacy_notice_id:
            match = next((item for item in notices if _string(item.get("id")) == legacy_notice_id), None)
            if match is None:
                raise ApiError(f"Legacy notice source not found: {legacy_notice_id}")
            manifest["notice_enabled"] = True
            manifest["notice"] = notice_to_legacy(match)
        elif legacy_notice_enabled is False:
            manifest["notice_enabled"] = False
            manifest["notice"] = None
        self.write_json(self.manifest_path, manifest)
        return self.load_all()

    def save_updates(self, payload: dict[str, Any]) -> dict[str, Any]:
        manifest = self.load_manifest()
        updates = [normalize_update(item) for item in _list(payload.get("updates")) if isinstance(item, dict)]
        manifest["updates"] = updates
        syncs = _list(payload.get("legacy_syncs"))
        if syncs:
            version_info = manifest.get("version_info")
            if not isinstance(version_info, dict):
                version_info = {}
            for raw_sync in syncs:
                sync = _dict(raw_sync)
                update_id = _string(sync.get("id"))
                update = next((item for item in updates if _string(item.get("id")) == update_id), None)
                if update is None:
                    raise ApiError(f"Legacy update source not found: {update_id}")
                platform = _string(sync.get("platform") or update.get("platform")).lower()
                if not platform:
                    raise ApiError("Legacy update sync requires a platform")
                version_info[platform] = update_to_legacy_version_info(update)
            manifest["version_info"] = version_info
        self.write_json(self.manifest_path, manifest)
        return self.load_all()

    def save_donors(self, payload: dict[str, Any]) -> dict[str, Any]:
        donors = [normalize_donor(item) for item in _list(payload.get("donors")) if isinstance(item, dict)]
        confirm = bool(payload.get("confirm_referenced_deletes"))
        old_donors = self.load_donors()
        old_ids = {_string(item.get("id")) for item in old_donors if isinstance(item, dict)}
        new_ids = {_string(item.get("id")) for item in donors}
        deleted = {item for item in old_ids - new_ids if item}
        refs = self.donor_references(self.load_announcements(self.load_manifest()))
        blocked = {donor_id: refs.get(donor_id, []) for donor_id in deleted if refs.get(donor_id)}
        if blocked and not confirm:
            raise ApiError(
                json.dumps({"referencedDonors": blocked}, ensure_ascii=False),
                HTTPStatus.CONFLICT,
            )
        self.write_json(self.donors_path, donors)
        return self.load_all()

    def upload_asset(self, payload: dict[str, Any]) -> dict[str, Any]:
        original_filename = _string(payload.get("filename"))
        filename = safe_filename(original_filename)
        data_url = _string(payload.get("data"))
        if not filename:
            raise ApiError("Asset filename is required")
        suffix = pathlib.Path(filename).suffix.lower()
        if suffix not in SAFE_ASSET_SUFFIXES:
            raise ApiError(f"Unsupported asset suffix: {suffix}")
        if payload.get("auto_name"):
            name_seed = " ".join(
                item
                for item in [
                    _string(payload.get("name") or payload.get("donor_name")),
                    _string(payload.get("donor_id")),
                ]
                if item
            )
            filename = generated_asset_filename(
                filename,
                name_seed=name_seed,
                path_seed=_string(payload.get("path") or payload.get("source_path") or original_filename),
            )
        if "," in data_url and data_url.lower().startswith("data:"):
            raw = data_url.split(",", 1)[1]
        else:
            raw = data_url
        try:
            content = base64.b64decode(raw, validate=True)
        except ValueError as exc:
            raise ApiError("Asset data must be base64 encoded") from exc
        if not content:
            raise ApiError("Asset data is empty")
        target = self._assert_write_allowed(self.assets_root / filename)
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            counter = 2
            while target.exists():
                target = self._assert_write_allowed(self.assets_root / f"{stem}-{counter}{suffix}")
                counter += 1
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return {
            "filename": target.name,
            "path": str(target),
            "url": asset_public_url(target.name),
        }

    def run_build_script(self, *, build: bool) -> dict[str, Any]:
        script = self.repo_root / ".github" / "scripts" / "build_update_config.py"
        if not script.exists():
            raise ApiError(f"Build script not found: {script}", HTTPStatus.NOT_FOUND)
        args = [sys.executable, str(script), "--root", "update"]
        if build:
            args.extend(["--output", "dist/update/latest.json"])
        else:
            args.append("--validate-only")
        completed = subprocess.run(
            args,
            cwd=str(self.repo_root),
            text=True,
            capture_output=True,
            timeout=60,
        )
        manifest = self.load_manifest()
        announcements = self.load_announcements(manifest)
        diagnostics = validate_v3(manifest)
        localized_diagnostics = self.localized_diagnostics(manifest, announcements)
        diagnostics = {
            "errors": [*diagnostics["errors"], *localized_diagnostics["errors"]],
            "warnings": [*diagnostics["warnings"], *localized_diagnostics["warnings"]],
        }
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "command": " ".join(args),
            "output": str(self.dist_latest) if build else "",
            "diagnostics": diagnostics,
        }


def normalize_announcement(raw: dict[str, Any]) -> dict[str, Any]:
    contents = _normalize_lang_map(raw.get("contents"))
    items: list[dict[str, Any]] = []
    for item in _list(raw.get("items")):
        if not isinstance(item, dict):
            continue
        category = _string(item.get("category")) or "improvement"
        item_contents = _normalize_lang_map(item.get("contents"))
        items.append({"category": category, "contents": item_contents})
    return {
        "id": _normalize_id(raw.get("id"), where="announcement.id") if _string(raw.get("id")) else "",
        "release_tag": _string(raw.get("release_tag")),
        "version": _string(raw.get("version")),
        "date": _string(raw.get("date")),
        "title": _string(raw.get("title")),
        "show_when_up_to_date": bool(raw.get("show_when_up_to_date")),
        "contents": contents,
        "new_donor_ids": [_string(item) for item in _list(raw.get("new_donor_ids")) if _string(item)],
        "items": items,
    }


def _parse_ai_json_content(content: Any) -> dict[str, Any]:
    text = _string(content)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    decoded = json.loads(text)
    if not isinstance(decoded, dict):
        raise ApiError("AI translation JSON must be an object.")
    return decoded


def normalize_localized_announcement(
    raw: dict[str, Any],
    *,
    announcement_id: str,
    locale: str,
    source_hash: str,
) -> dict[str, Any]:
    normalized_locale = _normalize_locale_tag(locale)
    if normalized_locale not in SUPPORTED_LOCALES:
        raise ApiError(f"Unsupported locale: {locale!r}")
    items: list[dict[str, Any]] = []
    for item in _list(raw.get("items")):
        if not isinstance(item, dict):
            continue
        category = _string(item.get("category")) or "improvement"
        contents = _read_lines(item.get("contents"))
        items.append({"category": category, "contents": contents})
    return {
        "id": _normalize_id(announcement_id, where="announcement.id"),
        "locale": normalized_locale,
        "title": _string(raw.get("title")),
        "summary": _read_lines(raw.get("summary") or raw.get("contents")),
        "items": items,
        "translation": {
            "source_locale": SOURCE_LOCALE,
            "source_hash": source_hash,
            "status": "ai_draft",
        },
    }


def normalize_localized_announcement_for_save(
    raw: dict[str, Any],
    *,
    announcement_id: str,
    locale: str,
    source_hash: str,
    status: str,
) -> dict[str, Any]:
    normalized = normalize_localized_announcement(
        raw,
        announcement_id=announcement_id,
        locale=locale,
        source_hash=source_hash,
    )
    translation = _dict(raw.get("translation"))
    normalized["translation"] = {
        "source_locale": _normalize_locale_tag(translation.get("source_locale")) or SOURCE_LOCALE,
        "source_hash": source_hash,
        "status": _translation_status(status),
    }
    return normalized


def normalize_notice(raw: dict[str, Any]) -> dict[str, Any]:
    audience = _dict(raw.get("audience"))
    display = _dict(raw.get("display"))
    content = _dict(raw.get("content"))
    title = _dict(content.get("title"))
    body = _normalize_lang_map(content.get("body") or content.get("contents"))
    out: dict[str, Any] = {
        "id": _string(raw.get("id")),
        "revision": int(raw.get("revision") or 1),
        "status": _string(raw.get("status")) or "draft",
        "priority": int(raw.get("priority") or 0),
        "severity": _string(raw.get("severity")) or "info",
        "publish_at": _string(raw.get("publish_at") or raw.get("publishAt")),
        "expire_at": _string(raw.get("expire_at") or raw.get("expireAt")),
        "audience": {
            "platforms": [_string(item).lower() for item in _list(audience.get("platforms")) if _string(item)],
            "channels": [_string(item).lower() for item in _list(audience.get("channels")) if _string(item)],
            "min_app_version": _string(audience.get("min_app_version") or audience.get("minAppVersion")),
            "max_app_version": _string(audience.get("max_app_version") or audience.get("maxAppVersion")),
        },
        "display": {
            "surface": _string(display.get("surface")) or "startup_dialog",
            "dismiss_policy": _string(display.get("dismiss_policy") or display.get("dismissPolicy")) or "once_per_revision",
            "blocking": bool(display.get("blocking")),
        },
        "content": {
            "title": {
                "zh": _string(title.get("zh")),
                "en": _string(title.get("en")),
            },
            "body": body,
        },
    }
    if not out["publish_at"]:
        out.pop("publish_at")
    if not out["expire_at"]:
        out.pop("expire_at")
    return out


def normalize_update(raw: dict[str, Any]) -> dict[str, Any]:
    audience = _dict(raw.get("audience"))
    out: dict[str, Any] = {
        "id": _string(raw.get("id")),
        "status": _string(raw.get("status")) or "draft",
        "priority": int(raw.get("priority") or 0),
        "platform": _string(raw.get("platform")).lower(),
        "channel": _string(raw.get("channel")).lower(),
        "version": _string(raw.get("version") or raw.get("latest_version")),
        "force": bool(raw.get("force") or raw.get("force_update") or raw.get("is_force")),
        "download_url": _string(raw.get("download_url") or raw.get("downloadUrl") or raw.get("url")),
        "release_note_id": _string(raw.get("release_note_id") or raw.get("releaseNoteId")),
        "publish_at": _string(raw.get("publish_at") or raw.get("publishAt")),
        "expire_at": _string(raw.get("expire_at") or raw.get("expireAt")),
        "audience": {
            "platforms": [_string(item).lower() for item in _list(audience.get("platforms")) if _string(item)],
            "channels": [_string(item).lower() for item in _list(audience.get("channels")) if _string(item)],
            "min_app_version": _string(audience.get("min_app_version") or audience.get("minAppVersion")),
            "max_app_version": _string(audience.get("max_app_version") or audience.get("maxAppVersion")),
        },
    }
    if not out["expire_at"]:
        out.pop("expire_at")
    return out


def normalize_donor(raw: dict[str, Any]) -> dict[str, str]:
    return {
        "id": _string(raw.get("id") or raw.get("uid")),
        "name": _string(raw.get("name")),
        "avatar": _string(raw.get("avatar") or raw.get("avatar_url")),
    }


def notice_to_legacy(notice: dict[str, Any]) -> dict[str, Any]:
    content = _dict(notice.get("content"))
    title = _dict(content.get("title"))
    return {
        "title": title.get("zh") or title.get("en") or _string(notice.get("id")),
        "contents": _normalize_lang_map(content.get("body") or content.get("contents")),
    }


def update_to_legacy_version_info(update: dict[str, Any]) -> dict[str, Any]:
    return {
        "latest_version": _string(update.get("version")),
        "force_update": bool(update.get("force")),
        "update_source": _string(update.get("channel")),
        "url": _string(update.get("download_url") or update.get("url")),
        "publish_at": _string(update.get("publish_at") or update.get("publishAt")),
    }


def filename_leaf(raw: str) -> str:
    return re.split(r"[\\/]+", _string(raw))[-1]


def safe_filename(raw: str) -> str:
    filename = filename_leaf(raw)
    filename = re.sub(r"[^A-Za-z0-9._ -]+", "_", filename).strip(" .")
    return filename[:160]


def safe_asset_slug(*parts: str) -> str:
    raw = " ".join(_string(part) for part in parts if _string(part))
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_").lower()
    if slug:
        return slug[:80]
    if raw:
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return "avatar"


def generated_asset_stem_slug(path_seed: str, original_filename: str) -> str:
    stem = pathlib.Path(filename_leaf(path_seed) or filename_leaf(original_filename)).stem
    stem = re.sub(r"^\d{8}[ _-]?\d{6}[_ -]+", "", stem)
    return safe_asset_slug(stem)


def compose_asset_slug(name_seed: str, path_seed: str, original_filename: str) -> str:
    name_slug = safe_asset_slug(name_seed) if _string(name_seed) else ""
    stem_slug = generated_asset_stem_slug(path_seed, original_filename)
    if not name_slug:
        return stem_slug or "avatar"
    if not stem_slug:
        return name_slug
    if name_slug == stem_slug or name_slug.endswith(f"_{stem_slug}") or stem_slug.endswith(f"_{name_slug}"):
        return name_slug
    return safe_asset_slug(name_slug, stem_slug)


def generated_asset_filename(original_filename: str, *, name_seed: str = "", path_seed: str = "") -> str:
    original = filename_leaf(original_filename)
    suffix = pathlib.Path(original).suffix.lower()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{stamp}_{compose_asset_slug(name_seed, path_seed, original)}{suffix}"


def asset_public_url(filename: str) -> str:
    return f"{ASSET_PUBLIC_BASE_URL}{quote(filename)}"


def validate_v3(manifest: dict[str, Any]) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    ids: set[str] = set()
    release_ids = {
        _string(item.get("id") or item.get("version"))
        for item in _list(manifest.get("release_notes"))
        if isinstance(item, dict)
    }
    for kind in ("notices", "updates"):
        items = _list(manifest.get(kind))
        for index, raw in enumerate(items):
            if not isinstance(raw, dict):
                errors.append(f"{kind}[{index}] must be an object.")
                continue
            path = f"{kind[:-1]}[{index}]"
            item_id = _string(raw.get("id"))
            if not item_id:
                errors.append(f"{path}.id is required.")
            elif item_id in ids:
                errors.append(f"Duplicate announcement id: {item_id}.")
            else:
                ids.add(item_id)
            status = _string(raw.get("status")).lower()
            if status == "draft":
                errors.append(f"{path} uses draft status in production config.")
            publish_at = _parse_datetime(raw.get("publish_at") or raw.get("publishAt"))
            expire_at = _parse_datetime(raw.get("expire_at") or raw.get("expireAt"))
            if status == "public" and publish_at is None:
                errors.append(f"{path}.publish_at is required for public items.")
            if publish_at and expire_at:
                if expire_at <= publish_at:
                    errors.append(f"{path}.expire_at must be after publish_at.")
                if (expire_at - publish_at).days > 45:
                    warnings.append(f"{path} has an expiry window longer than 45 days.")
            encoded = json.dumps(raw, ensure_ascii=False).lower()
            if "test only" in encoded or "debug" in encoded or "\u8349\u7a3f" in encoded or "\u6d4b\u8bd5\u516c\u544a" in encoded:
                warnings.append(f"{path} contains wording that looks like test content.")
            if kind == "notices":
                content = _dict(raw.get("content")) or raw
                body = content.get("body") or content.get("contents")
                if not _has_content(body):
                    errors.append(f"{path} content body is required.")
                if not _has_english(body):
                    warnings.append(f"{path} does not include English body content.")
            else:
                force = bool(raw.get("force") or raw.get("force_update") or raw.get("is_force"))
                url = _string(raw.get("download_url") or raw.get("downloadUrl") or raw.get("url"))
                if force and not _is_http_url(url):
                    errors.append(f"{path} forced update requires a valid HTTP(S) download URL.")
                release_note_id = _string(raw.get("release_note_id") or raw.get("releaseNoteId"))
                if release_note_id and release_ids and release_note_id not in release_ids:
                    warnings.append(f"Update references missing release note: {release_note_id}.")
                elif not release_note_id:
                    warnings.append(f"{path} does not reference a release note id.")
                channel = _string(raw.get("channel")).lower()
                if channel == "play" and url.lower().endswith(".apk"):
                    warnings.append(f"{path} Play-channel update points to an APK URL.")
    return {"errors": errors, "warnings": warnings}


class ManagerHandler(BaseHTTPRequestHandler):
    repo: ConfigRepository
    static_root: pathlib.Path

    server_version = "MemoFlowConfigManager/1.0"

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/config":
                self._send_json({"ok": True, "data": self.repo.load_all()})
                return
            if parsed.path == "/api/announcement/localized":
                params = parse_qs(parsed.query)
                data = self.repo.localized_editor_payload(
                    (params.get("id") or [""])[0],
                    (params.get("locale") or [""])[0],
                )
                self._send_json({"ok": True, "data": data})
                return
            if parsed.path == "/api/git/commit-ranges":
                params = parse_qs(parsed.query)
                data = self.repo.git_commit_range_options(
                    {
                        "repoPath": (params.get("repoPath") or params.get("repo_path") or [""])[0],
                        "tagLimit": (params.get("tagLimit") or params.get("tag_limit") or ["12"])[0],
                    }
                )
                self._send_json({"ok": True, "data": data})
                return
            if parsed.path == "/api/git/commits":
                params = parse_qs(parsed.query)
                data = self.repo.git_commit_options(
                    {
                        "repoPath": (params.get("repoPath") or params.get("repo_path") or [""])[0],
                        "limit": (params.get("limit") or ["all"])[0],
                    }
                )
                self._send_json({"ok": True, "data": data})
                return
            if parsed.path == "/api/preview-summary":
                self._send_json({"ok": True, "data": self.repo.generated_summary()})
                return
            self._serve_static(parsed.path)
        except ApiError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=exc.status)
        except Exception as exc:  # noqa: BLE001 - local tool must report diagnostics
            self._send_json({"ok": False, "error": str(exc)}, status=500)

    def do_POST(self) -> None:
        try:
            payload = self._read_json_body()
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/announcement/save":
                data = self.repo.save_announcement(payload)
            elif path == "/api/announcement/create":
                data = self.repo.create_announcement(payload)
            elif path == "/api/announcement/set-latest":
                data = self.repo.set_latest_announcement(payload)
            elif path == "/api/announcement/delete":
                data = self.repo.delete_announcement(payload)
            elif path == "/api/announcement/generate-from-commits":
                data = self.repo.generate_announcement_items_from_commits(payload)
            elif path == "/api/announcement/ai-summary":
                data = self.repo.generate_announcement_summary_with_ai(payload)
            elif path == "/api/announcement/ai-translate":
                data = self.repo.translate_announcement_with_ai(payload)
            elif path == "/api/announcement/localized/save":
                data = self.repo.save_localized_announcement(payload)
            elif path == "/api/announcement/localized/delete":
                data = self.repo.delete_localized_announcement(payload)
            elif path == "/api/ai/settings/save":
                data = self.repo.save_ai_settings(payload)
            elif path == "/api/notices/save":
                data = self.repo.save_notices(payload)
            elif path == "/api/updates/save":
                data = self.repo.save_updates(payload)
            elif path == "/api/donors/save":
                data = self.repo.save_donors(payload)
            elif path == "/api/assets/upload":
                data = self.repo.upload_asset(payload)
            elif path == "/api/validate":
                data = self.repo.run_build_script(build=False)
            elif path == "/api/build":
                data = self.repo.run_build_script(build=True)
            else:
                raise ApiError(f"Unknown API endpoint: {path}", HTTPStatus.NOT_FOUND)
            self._send_json({"ok": True, "data": data})
        except ApiError as exc:
            detail: Any = str(exc)
            try:
                detail = json.loads(str(exc))
            except json.JSONDecodeError:
                pass
            self._send_json({"ok": False, "error": detail}, status=exc.status)
        except Exception as exc:  # noqa: BLE001 - local tool must report diagnostics
            self._send_json({"ok": False, "error": str(exc)}, status=500)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length > MAX_BODY_BYTES:
            raise ApiError("Request body is too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ApiError(f"Invalid JSON body: {exc}") from exc
        if not isinstance(data, dict):
            raise ApiError("JSON object body required")
        return data

    def _serve_static(self, request_path: str) -> None:
        path = unquote(request_path)
        if path in ("", "/"):
            path = "/manager.html"
        candidate = (self.static_root / path.lstrip("/")).resolve()
        if not _is_relative_to(candidate, self.static_root.resolve()) or not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/javascript":
            content_type = f"{content_type}; charset=utf-8"
        data = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[manager] {self.address_string()} - {fmt % args}")


def find_repo_root(start: pathlib.Path) -> pathlib.Path:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "update" / "manifest.json").exists() and (candidate / ".github" / "scripts" / "build_update_config.py").exists():
            return candidate
    raise SystemExit("Could not locate memoflow_config repository root.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local MemoFlow config manager")
    parser.add_argument("--host", default=HOST, help="bind host, default 127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="bind port")
    parser.add_argument("--repo-root", default="", help="explicit memoflow_config repository root")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_dir = pathlib.Path(__file__).resolve().parent
    repo_root = pathlib.Path(args.repo_root).resolve() if args.repo_root else find_repo_root(script_dir)
    repo = ConfigRepository(repo_root)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("Refusing to bind non-loopback host. Use 127.0.0.1.")
    ManagerHandler.repo = repo
    ManagerHandler.static_root = repo.config_root
    try:
        server = ThreadingHTTPServer((args.host, args.port), ManagerHandler)
    except OSError:
        if args.port != 0:
            print(f"Port {args.port} is busy, falling back to an available local port.")
            server = ThreadingHTTPServer((args.host, 0), ManagerHandler)
        else:
            raise
    actual_port = server.server_address[1]
    print(f"MemoFlow config manager: http://{args.host}:{actual_port}/")
    print(f"Repository root: {repo.repo_root}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
