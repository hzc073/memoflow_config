#!/usr/bin/env python3
"""Build and validate MemoFlow update config from split files.

Directory layout (default root: update):
  manifest.json
  donors.json (optional)
  announcements/{id}.json

`manifest.json` keeps global fields and index pointers:
  - schema_version
  - version_info
  - notice_enabled / notice / debug_announcement / debug_announcement_source
  - donors_file (optional, default: donors.json)
  - announcement_ids (list[int|string])
  - latest_announcement_id (int|string)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from copy import deepcopy
from typing import Any, Dict, List, Tuple


SUPPORTED_LOCALES = ("zh-Hans", "zh-Hant-TW", "en", "ja", "de", "pt-BR", "ko")
SOURCE_LOCALE = "zh-Hans"
FALLBACK_LOCALE = "en"
V2_COMPAT_LOCALES = ("zh", "en")
LOCALE_ALIAS_KEYS = {
    "zh",
    "zh-cn",
    "zh-hans",
    "zh-sg",
    "zh-tw",
    "zh-hk",
    "zh-mo",
    "zh-hant",
    "zh-hant-tw",
    "en",
    "en-us",
    "en-gb",
    "ja",
    "de",
    "pt",
    "pt-br",
    "ko",
}
DELIVERY_CONTROL_FIELDS = {
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


class ConfigError(Exception):
    pass


def _read_json(path: pathlib.Path) -> Dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"failed reading {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid json in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"json object required in {path}")
    return data


def _read_json_list(path: pathlib.Path) -> List[Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"failed reading {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid json in {path}: {exc}") from exc
    if not isinstance(data, list):
        raise ConfigError(f"json array required in {path}")
    return data


def _read_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _read_text_list(value: Any) -> List[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            text = _read_string(item)
            if text:
                out.append(text)
        return out
    return []


def _normalize_locale_tag(value: Any) -> str:
    text = _read_string(value).replace("_", "-").lower()
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


def _locale_lookup_keys(locale: str) -> List[str]:
    normalized = _normalize_locale_tag(locale)
    if normalized == "zh-Hans":
        return ["zh-Hans", "zh", "zh-CN", "zh-hans", "zh_cn"]
    if normalized == "zh-Hant-TW":
        return ["zh-Hant-TW", "zh-Hant", "zh-TW", "zh_hant_tw", "zh_tw", "zh"]
    if normalized == "pt-BR":
        return ["pt-BR", "pt", "pt_br"]
    if normalized == "en":
        return ["en", "en-US", "en_us"]
    if normalized:
        return [normalized]
    return []


def _canonical_locale_key(key: Any) -> str:
    text = _read_string(key).replace("_", "-").lower()
    if text.startswith("zh-hant") or text in {"zh-tw", "zh-hk", "zh-mo"}:
        return "zh-Hant-TW"
    if text.startswith("zh"):
        return "zh-Hans"
    if text.startswith("en"):
        return "en"
    if text.startswith("pt"):
        return "pt-BR"
    if text.startswith("ja"):
        return "ja"
    if text.startswith("de"):
        return "de"
    if text.startswith("ko"):
        return "ko"
    return text.split("-", 1)[0] if text else ""


def _content_key_for_locale(locale: str) -> str:
    normalized = _normalize_locale_tag(locale)
    return normalized or FALLBACK_LOCALE


def _select_localized_values(
    value: Any,
    locale: str,
    *,
    fallback_locale: str = FALLBACK_LOCALE,
) -> Tuple[List[str], str]:
    if isinstance(value, dict):
        by_locale: Dict[str, List[str]] = {}
        for raw_key, raw_value in value.items():
            canonical = _canonical_locale_key(raw_key)
            values = _read_text_list(raw_value)
            if canonical and values and canonical not in by_locale:
                by_locale[canonical] = values
        requested = _normalize_locale_tag(locale)
        if requested and requested in by_locale:
            return by_locale[requested], requested
        fallback = _normalize_locale_tag(fallback_locale)
        if fallback and fallback in by_locale:
            return by_locale[fallback], fallback
        return [], ""
    values = _read_text_list(value)
    if values:
        normalized = _normalize_locale_tag(locale) or FALLBACK_LOCALE
        return values, normalized
    return [], ""


def _select_localized_text(
    value: Any,
    locale: str,
    *,
    fallback_locale: str = FALLBACK_LOCALE,
) -> Tuple[str, str]:
    if isinstance(value, dict):
        for key in _locale_lookup_keys(locale):
            text = _read_string(value.get(key))
            if text:
                return text, _normalize_locale_tag(locale) or locale
        for key in _locale_lookup_keys(fallback_locale):
            text = _read_string(value.get(key))
            if text:
                return text, _normalize_locale_tag(fallback_locale) or fallback_locale
        return "", ""
    text = _read_string(value)
    if text:
        return text, _normalize_locale_tag(locale) or locale
    return "", ""


def _normalize_id(value: Any, *, where: str) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return text
    raise ConfigError(f"invalid announcement id in {where}: {value!r}")


def _looks_like_locale_map(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    keys = {_read_string(key).replace("_", "-").lower() for key in value.keys()}
    return bool(keys & LOCALE_ALIAS_KEYS)


def _validate_single_locale_content(
    data: Dict[str, Any],
    *,
    expected_locale: str,
    path: pathlib.Path,
) -> None:
    declared_locale = _normalize_locale_tag(data.get("locale"))
    if declared_locale != expected_locale:
        raise ConfigError(
            f"locale mismatch in {path}: expected {expected_locale}, got {data.get('locale')!r}"
        )
    for field in DELIVERY_CONTROL_FIELDS:
        if field in data:
            raise ConfigError(
                f"localized announcement file must not define delivery field {field!r}: {path}"
            )
    for field in ("title", "summary", "contents"):
        if _looks_like_locale_map(data.get(field)):
            raise ConfigError(f"{path}.{field} must contain only one locale")
    for index, raw_item in enumerate(data.get("items") if isinstance(data.get("items"), list) else []):
        if not isinstance(raw_item, dict):
            continue
        if _looks_like_locale_map(raw_item.get("contents")):
            raise ConfigError(f"{path}.items[{index}].contents must contain only one locale")
        for field in DELIVERY_CONTROL_FIELDS:
            if field in raw_item:
                raise ConfigError(
                    f"localized announcement item must not define delivery field {field!r}: {path}"
                )
    translation = data.get("translation")
    if isinstance(translation, dict):
        status = _read_string(translation.get("status")).lower()
        if status in {"ai_draft", "draft", "stale", "needs_review", "unreviewed"}:
            raise ConfigError(
                f"{path} contains AI/stale translation status {status!r}; review before publishing"
            )


def _load_localized_announcements(
    root: pathlib.Path,
    ids: List[str],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    localized: Dict[str, Dict[str, Dict[str, Any]]] = {
        locale: {} for locale in SUPPORTED_LOCALES
    }
    locales_root = root / "locales"
    if not locales_root.exists():
        return localized
    expected_ids = set(ids)
    for locale in SUPPORTED_LOCALES:
        ann_dir = locales_root / locale / "announcements"
        if not ann_dir.exists():
            continue
        for path in sorted(ann_dir.glob("*.json")):
            data = _read_json(path)
            ann_id = _normalize_id(data.get("id"), where=str(path))
            if ann_id not in expected_ids:
                raise ConfigError(f"localized announcement id is not referenced by manifest: {path}")
            _validate_single_locale_content(
                data,
                expected_locale=locale,
                path=path,
            )
            localized[locale][ann_id] = data
    return localized


def _announcement_source_hash(announcement: Dict[str, Any], source_locale: str = "zh-Hans") -> str:
    payload = {
        "title": _read_string(announcement.get("title")),
        "summary": _select_localized_values(
            announcement.get("contents"),
            source_locale,
            fallback_locale=source_locale,
        )[0],
        "items": [
            {
                "category": _read_string(item.get("category")) if isinstance(item, dict) else "",
                "contents": _select_localized_values(
                    item.get("contents") if isinstance(item, dict) else None,
                    source_locale,
                    fallback_locale=source_locale,
                )[0],
            }
            for item in (announcement.get("items") if isinstance(announcement.get("items"), list) else [])
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_translation_hashes(
    localized_announcements: Dict[str, Dict[str, Dict[str, Any]]],
    announcements: Dict[str, Dict[str, Any]],
) -> None:
    for _locale, by_id in localized_announcements.items():
        for ann_id, data in by_id.items():
            translation = data.get("translation")
            if not isinstance(translation, dict):
                continue
            source_hash = _read_string(translation.get("source_hash"))
            if not source_hash:
                continue
            source_locale = _normalize_locale_tag(translation.get("source_locale")) or "zh-Hans"
            current = _announcement_source_hash(announcements[ann_id], source_locale)
            if source_hash != current:
                raise ConfigError(
                    f"localized announcement {ann_id} is stale for {data.get('locale')!r}; regenerate or review translation"
                )


def _load_announcements(
    root: pathlib.Path,
    ids: List[str],
) -> Dict[str, Dict[str, Any]]:
    announcements: Dict[str, Dict[str, Any]] = {}
    ann_dir = root / "announcements"
    for ann_id in ids:
        path = ann_dir / f"{ann_id}.json"
        if not path.exists():
            raise ConfigError(f"missing announcement file: {path}")
        data = _read_json(path)
        file_id = _normalize_id(data.get("id"), where=str(path))
        if file_id != ann_id:
            raise ConfigError(
                f"announcement id mismatch in {path}: expected {ann_id}, got {file_id}"
            )
        announcements[ann_id] = data
    return announcements


def _build_release_note(entry: Dict[str, Any]) -> Dict[str, Any] | None:
    version = str(entry.get("version", "")).strip()
    date_label = str(entry.get("date", "")).strip()
    items = entry.get("items")
    if not isinstance(items, list):
        items = []
    normalized_items: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", "")).strip()
        contents = item.get("contents")
        normalized_contents: Any
        if isinstance(contents, dict):
            localized: Dict[str, List[str]] = {}
            for key, value in contents.items():
                if not isinstance(key, str):
                    continue
                lang = key.strip().lower()
                if not lang:
                    continue
                if isinstance(value, str):
                    values = [value.strip()] if value.strip() else []
                elif isinstance(value, list):
                    values = [str(x).strip() for x in value if str(x).strip()]
                else:
                    values = []
                if values:
                    localized[lang] = values
            normalized_contents = localized
        elif isinstance(contents, str):
            normalized_contents = [contents.strip()] if contents.strip() else []
        elif isinstance(contents, list):
            normalized_contents = [str(x).strip() for x in contents if str(x).strip()]
        else:
            normalized_contents = []
        if not category and not normalized_contents:
            continue
        normalized_items.append(
            {
                "category": category,
                "contents": normalized_contents,
            }
        )
    if not version and not normalized_items:
        return None
    return {
        "version": version,
        "date": date_label,
        "items": normalized_items,
    }


def _locale_content_summary(
    announcement: Dict[str, Any],
    locale: str,
    localized: Dict[str, Dict[str, Dict[str, Any]]],
) -> Tuple[List[str], str]:
    ann_id = _normalize_id(announcement.get("id"), where="announcement.id")
    localized_item = localized.get(locale, {}).get(ann_id)
    if localized_item is not None:
        values = _read_text_list(localized_item.get("summary") or localized_item.get("contents"))
        if values:
            return values, locale
    if _normalize_locale_tag(locale) == SOURCE_LOCALE:
        values, content_locale = _select_localized_values(
            announcement.get("contents"),
            SOURCE_LOCALE,
            fallback_locale=SOURCE_LOCALE,
        )
        if values:
            return values, content_locale
    english_item = localized.get(FALLBACK_LOCALE, {}).get(ann_id)
    if english_item is not None:
        values = _read_text_list(english_item.get("summary") or english_item.get("contents"))
        if values:
            return values, FALLBACK_LOCALE
    return _select_localized_values(announcement.get("contents"), locale)


def _locale_content_title(
    announcement: Dict[str, Any],
    locale: str,
    localized: Dict[str, Dict[str, Dict[str, Any]]],
) -> str:
    ann_id = _normalize_id(announcement.get("id"), where="announcement.id")
    localized_item = localized.get(locale, {}).get(ann_id)
    if localized_item is not None:
        title = _read_string(localized_item.get("title"))
        if title:
            return title
    if _normalize_locale_tag(locale) == SOURCE_LOCALE:
        title, _ = _select_localized_text(
            announcement.get("title"),
            SOURCE_LOCALE,
            fallback_locale=SOURCE_LOCALE,
        )
        if title:
            return title
    english_item = localized.get(FALLBACK_LOCALE, {}).get(ann_id)
    if english_item is not None:
        title = _read_string(english_item.get("title"))
        if title:
            return title
    title, _ = _select_localized_text(announcement.get("title"), locale)
    return title or _read_string(announcement.get("title"))


def _locale_content_items(
    announcement: Dict[str, Any],
    locale: str,
    localized: Dict[str, Dict[str, Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    ann_id = _normalize_id(announcement.get("id"), where="announcement.id")
    localized_item = localized.get(locale, {}).get(ann_id)
    if localized_item is not None and isinstance(localized_item.get("items"), list):
        out: List[Dict[str, Any]] = []
        for raw_item in localized_item["items"]:
            if not isinstance(raw_item, dict):
                continue
            category = _read_string(raw_item.get("category"))
            values = _read_text_list(raw_item.get("contents"))
            if category or values:
                out.append({"category": category, "contents": values})
        if any(item["contents"] for item in out):
            return out

    if _normalize_locale_tag(locale) == SOURCE_LOCALE:
        out = []
        for raw_item in announcement.get("items") if isinstance(announcement.get("items"), list) else []:
            if not isinstance(raw_item, dict):
                continue
            values, content_locale = _select_localized_values(
                raw_item.get("contents"),
                SOURCE_LOCALE,
                fallback_locale=SOURCE_LOCALE,
            )
            category = _read_string(raw_item.get("category"))
            if category or values:
                out.append(
                    {
                        "category": category,
                        "contents": values,
                        "_content_locale": content_locale,
                    }
                )
        if any(item["contents"] for item in out):
            return out

    english_item = localized.get(FALLBACK_LOCALE, {}).get(ann_id)
    if english_item is not None and isinstance(english_item.get("items"), list):
        out = []
        for raw_item in english_item["items"]:
            if not isinstance(raw_item, dict):
                continue
            category = _read_string(raw_item.get("category"))
            values = _read_text_list(raw_item.get("contents"))
            if category or values:
                out.append({"category": category, "contents": values})
        if any(item["contents"] for item in out):
            return out

    out = []
    for raw_item in announcement.get("items") if isinstance(announcement.get("items"), list) else []:
        if not isinstance(raw_item, dict):
            continue
        values, content_locale = _select_localized_values(raw_item.get("contents"), locale)
        category = _read_string(raw_item.get("category"))
        if category or values:
            out.append(
                {
                    "category": category,
                    "contents": values,
                    "_content_locale": content_locale,
                }
            )
    return out


def _build_localized_announcement(
    announcement: Dict[str, Any],
    locale: str,
    localized: Dict[str, Dict[str, Dict[str, Any]]],
) -> Dict[str, Any]:
    summary, summary_locale = _locale_content_summary(announcement, locale, localized)
    content_locale = summary_locale or _normalize_locale_tag(locale) or FALLBACK_LOCALE
    return {
        "id": _normalize_id(announcement.get("id"), where="announcement.id"),
        "title": _locale_content_title(announcement, locale, localized),
        "show_when_up_to_date": bool(announcement.get("show_when_up_to_date", False)),
        "contents": {
            _content_key_for_locale(content_locale): summary,
        }
        if summary
        else {},
        "new_donor_ids": announcement.get("new_donor_ids", []),
    }


def _build_localized_release_note(
    announcement: Dict[str, Any],
    locale: str,
    localized: Dict[str, Dict[str, Dict[str, Any]]],
) -> Dict[str, Any] | None:
    version = _read_string(announcement.get("version"))
    date_label = _read_string(announcement.get("date"))
    items: List[Dict[str, Any]] = []
    for item in _locale_content_items(announcement, locale, localized):
        values = _read_text_list(item.get("contents"))
        if not values:
            continue
        item_locale = _read_string(item.get("_content_locale")) or locale
        items.append(
            {
                "category": _read_string(item.get("category")),
                "contents": {
                    _content_key_for_locale(item_locale): values,
                },
            }
        )
    if not version and not items:
        return None
    return {
        "version": version,
        "date": date_label,
        "items": items,
    }


def _localize_notice_content(value: Any, locale: str) -> Dict[str, Any]:
    content = value if isinstance(value, dict) else {}
    title, title_locale = _select_localized_text(content.get("title"), locale)
    body, body_locale = _select_localized_values(
        content.get("body") or content.get("contents"),
        locale,
    )
    out: Dict[str, Any] = {}
    if title:
        out["title"] = {_content_key_for_locale(title_locale or locale): title}
    if body:
        out["body"] = {_content_key_for_locale(body_locale or locale): body}
    return out


def _localize_notice_candidates(items: Any, locale: str) -> List[Any]:
    if not isinstance(items, list):
        return []
    out: List[Any] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item = deepcopy(raw)
        item["content"] = _localize_notice_content(item.get("content"), locale)
        out.append(item)
    return out


def _apply_overrides(
    merged: Dict[str, Any],
    *,
    tag_version: str,
    android_url: str,
    ios_url: str,
    windows_url: str,
    android_version: str,
    ios_version: str,
    windows_version: str,
) -> None:
    version_info = merged.get("version_info")
    if not isinstance(version_info, dict):
        return

    def get_platform(name: str) -> Dict[str, Any] | None:
        value = version_info.get(name)
        if isinstance(value, dict):
            return value
        return None

    def set_nonempty(target: Dict[str, Any] | None, key: str, value: str) -> None:
        if target is None:
            return
        text = value.strip()
        if text:
            target[key] = text

    android = get_platform("android")
    ios = get_platform("ios")
    windows = get_platform("windows")

    set_nonempty(android, "url", android_url)
    set_nonempty(ios, "url", ios_url)
    set_nonempty(windows, "url", windows_url)

    set_nonempty(android, "latest_version", android_version)
    set_nonempty(ios, "latest_version", ios_version)
    set_nonempty(windows, "latest_version", windows_version)

    tag_text = tag_version.strip()
    if tag_text:
        if android is not None and android_url.strip() and not android_version.strip():
            android["latest_version"] = tag_text
        if windows is not None and windows_url.strip() and not windows_version.strip():
            windows["latest_version"] = tag_text
        if ios is not None and ios_url.strip() and not ios_version.strip():
            ios["latest_version"] = tag_text


def _build_localized_configs(
    merged: Dict[str, Any],
    announcements: Dict[str, Dict[str, Any]],
    announcement_ids: List[str],
    latest_announcement_id: str,
    localized_announcements: Dict[str, Dict[str, Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    release_note_ids = sorted(
        announcement_ids,
        key=lambda ann_id: int(ann_id),
        reverse=True,
    )
    out: Dict[str, Dict[str, Any]] = {}
    for locale in SUPPORTED_LOCALES:
        localized = deepcopy(merged)
        localized["schema_version"] = max(int(localized.get("schema_version") or 0), 3)
        localized["locale"] = locale
        localized["fallback_locale"] = FALLBACK_LOCALE
        localized["announcement"] = _build_localized_announcement(
            announcements[latest_announcement_id],
            locale,
            localized_announcements,
        )
        localized["release_notes"] = [
            release_note
            for release_note in (
                _build_localized_release_note(
                    announcements[ann_id],
                    locale,
                    localized_announcements,
                )
                for ann_id in release_note_ids
            )
            if release_note is not None
        ]
        if "notices" in localized:
            localized["notices"] = _localize_notice_candidates(
                localized.get("notices"),
                locale,
            )
        out[locale] = localized
    return out


def compile_update_bundle(
    root: pathlib.Path,
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]], Dict[str, Any]]:
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise ConfigError(f"manifest file not found: {manifest_path}")
    manifest = _read_json(manifest_path)
    schema_version = manifest.get("schema_version")
    if not isinstance(schema_version, int) or schema_version < 2:
        raise ConfigError("localized update config requires manifest.schema_version >= 2")

    announcement_ids_raw = manifest.get("announcement_ids")
    if not isinstance(announcement_ids_raw, list) or not announcement_ids_raw:
        raise ConfigError("manifest.announcement_ids must be a non-empty array")
    announcement_ids = [
        _normalize_id(value, where="manifest.announcement_ids")
        for value in announcement_ids_raw
    ]
    if len(set(announcement_ids)) != len(announcement_ids):
        raise ConfigError("manifest.announcement_ids contains duplicates")

    latest_raw = manifest.get("latest_announcement_id")
    latest_announcement_id = _normalize_id(latest_raw, where="manifest.latest_announcement_id")
    if latest_announcement_id not in announcement_ids:
        raise ConfigError(
            f"manifest.latest_announcement_id={latest_announcement_id} is not in announcement_ids"
        )

    announcements = _load_announcements(root, announcement_ids)
    localized_announcements = _load_localized_announcements(root, announcement_ids)
    _validate_translation_hashes(localized_announcements, announcements)

    donors_file = str(manifest.get("donors_file", "donors.json")).strip()
    donors: List[Any] = []
    if donors_file:
        donors_path = root / donors_file
        if donors_path.exists():
            donors = _read_json_list(donors_path)
        elif donors_file != "donors.json":
            raise ConfigError(f"manifest.donors_file not found: {donors_path}")

    active = announcements[latest_announcement_id]
    release_note_ids = sorted(
        announcement_ids,
        key=lambda ann_id: int(ann_id),
        reverse=True,
    )
    release_notes: List[Dict[str, Any]] = []
    for ann_id in release_note_ids:
        note = _build_release_note(announcements[ann_id])
        if note is not None:
            release_notes.append(note)

    merged = deepcopy(manifest)
    merged.pop("announcement_ids", None)
    merged.pop("latest_announcement_id", None)
    merged.pop("donors_file", None)
    merged.pop("announcement_tag_index", None)

    merged["announcement"] = {
        "id": latest_announcement_id,
        "title": str(active.get("title", "")).strip(),
        "show_when_up_to_date": bool(active.get("show_when_up_to_date", False)),
        "contents": active.get("contents", {}),
        "new_donor_ids": active.get("new_donor_ids", []),
    }
    merged["donors"] = donors
    merged["release_notes"] = release_notes
    localized_configs = _build_localized_configs(
        merged,
        announcements,
        announcement_ids,
        latest_announcement_id,
        localized_announcements,
    )

    summary = {
        "announcement_ids": announcement_ids,
        "latest_announcement_id": latest_announcement_id,
        "release_notes_count": len(release_notes),
        "donors_count": len(donors),
        "localized_outputs": list(localized_configs.keys()),
    }
    return merged, localized_configs, summary


def compile_update_config(root: pathlib.Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    merged, _localized_configs, summary = compile_update_bundle(root)
    return merged, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build MemoFlow update config")
    parser.add_argument("--root", default="update", help="config root directory")
    parser.add_argument("--output", default="dist/update/latest.json", help="output json path")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate split files only; do not write output",
    )
    parser.add_argument("--tag-version", default="", help="release tag version (without leading v)")
    parser.add_argument("--android-url", default="", help="override android url")
    parser.add_argument("--ios-url", default="", help="override ios url")
    parser.add_argument("--windows-url", default="", help="override windows url")
    parser.add_argument("--android-version", default="", help="override android latest_version")
    parser.add_argument("--ios-version", default="", help="override ios latest_version")
    parser.add_argument("--windows-version", default="", help="override windows latest_version")
    return parser.parse_args()


def _localized_output_path(output: pathlib.Path, locale: str) -> pathlib.Path:
    suffix = output.suffix or ".json"
    stem = output.name[: -len(suffix)] if output.name.endswith(suffix) else output.stem
    return output.with_name(f"{stem}.{locale}{suffix}")


def main() -> int:
    args = parse_args()
    root = pathlib.Path(args.root).resolve()
    try:
        merged, localized_configs, summary = compile_update_bundle(root)
        _apply_overrides(
            merged,
            tag_version=args.tag_version,
            android_url=args.android_url,
            ios_url=args.ios_url,
            windows_url=args.windows_url,
            android_version=args.android_version,
            ios_version=args.ios_version,
            windows_version=args.windows_version,
        )
        for localized in localized_configs.values():
            _apply_overrides(
                localized,
                tag_version=args.tag_version,
                android_url=args.android_url,
                ios_url=args.ios_url,
                windows_url=args.windows_url,
                android_version=args.android_version,
                ios_version=args.ios_version,
                windows_version=args.windows_version,
            )
    except ConfigError as exc:
        print(f"[update-config] error: {exc}", file=sys.stderr)
        return 1

    print(
        "[update-config] validated: "
        f"announcements={len(summary['announcement_ids'])}, "
        f"latest={summary['latest_announcement_id']}, "
        f"release_notes={summary['release_notes_count']}, "
        f"donors={summary['donors_count']}, "
        f"locales={len(summary['localized_outputs'])}"
    )

    if args.validate_only:
        return 0

    output = pathlib.Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        output.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        for locale, localized in localized_configs.items():
            localized_output = _localized_output_path(output, locale)
            localized_output.write_text(
                json.dumps(localized, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    except OSError as exc:
        print(f"[update-config] write failed: {exc}", file=sys.stderr)
        return 1

    print(f"[update-config] built: {output}")
    for locale in localized_configs:
        print(f"[update-config] built: {_localized_output_path(output, locale)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
