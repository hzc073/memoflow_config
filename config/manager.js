const state = {
  data: null,
  panel: "update",
  dirty: false,
  selectedAnnouncementId: "",
  selectedHistoryId: "",
  selectedLocalizationAnnouncementId: "",
  selectedLocalizationLocale: "en",
  localizedEditor: null,
  lastAiTranslation: null,
  commitRanges: [],
  commitChoices: [],
  selectedCommitRange: "",
  selectedNotice: 0,
  selectedUpdate: 0,
  selectedDonor: 0,
  draggedAnnouncementItemIndex: null,
};

const statusOptions = ["draft", "preview", "public", "archived"];
const severityOptions = ["info", "warning", "critical"];
const surfaceOptions = ["startup_dialog", "release_highlight"];
const dismissOptions = ["once_per_id", "once_per_revision", "every_start"];
const platformOptions = ["android", "windows", "ios", "macos", "linux", "web"];
const channelOptions = ["full", "play"];
const updatePriorityOptions = [
  { value: "0", label: "普通 (0)" },
  { value: "10", label: "较高 (10)" },
  { value: "50", label: "重要 (50)" },
  { value: "100", label: "紧急 (100)" },
];
const sourceLocale = "zh-Hans";
const localizedAnnouncementLocales = ["zh-Hant-TW", "en", "ja", "de", "pt-BR", "ko"];
const allLocales = [sourceLocale, ...localizedAnnouncementLocales];
const translationStatusOptions = ["ai_draft", "needs_review", "reviewed", "stale"];
const announcementCategoryOptions = [
  { value: "feature", label: "新增" },
  { value: "fix", label: "修复" },
  { value: "improvement", label: "优化" },
];
const localeLabels = {
  "zh-Hans": "简体中文",
  "zh-Hant-TW": "繁体中文",
  en: "English",
  ja: "日本語",
  de: "Deutsch",
  "pt-BR": "Português BR",
  ko: "한국어",
};
const optionLabels = {
  draft: "草稿",
  preview: "预览",
  public: "公开",
  archived: "已归档",
  info: "信息",
  warning: "警告",
  critical: "严重",
  startup_dialog: "启动弹窗",
  release_highlight: "更新亮点",
  once_per_id: "每个 ID 一次",
  once_per_revision: "每个修订一次",
  every_start: "每次启动",
  full: "完整渠道",
  play: "Google Play",
  android: "Android",
  windows: "Windows",
  ios: "iOS",
  macos: "macOS",
  linux: "Linux",
  web: "Web",
  ai_draft: "AI 草稿",
  needs_review: "待审核",
  reviewed: "已审核",
  stale: "源内容已变更",
  missing: "缺失",
  source: "源语言",
};

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function lines(value) {
  if (Array.isArray(value)) return value.map(String).filter((line) => line.trim());
  if (typeof value === "string") {
    return value
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
  }
  return [];
}

function textFromLines(value) {
  return lines(value).join("\n");
}

function commaList(value) {
  if (Array.isArray(value)) return value.map(String).filter(Boolean).join(", ");
  if (!value) return "";
  return String(value);
}

function parseCommaList(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function selectedValues(id) {
  const root = $(id);
  if (!root) return [];
  const source = root.selectedOptions
    ? Array.from(root.selectedOptions)
    : Array.from(root.querySelectorAll("[data-multi-choice]:checked"));
  return source
    .map((option) => option.value.trim())
    .filter(Boolean);
}

function normalizeLocaleTag(value) {
  const text = String(value || "").trim().replaceAll("_", "-").toLowerCase();
  if (!text) return "";
  if (["zh", "zh-cn", "zh-sg", "zh-hans"].includes(text)) return "zh-Hans";
  if (["zh-tw", "zh-hk", "zh-mo", "zh-hant", "zh-hant-tw"].includes(text)) return "zh-Hant-TW";
  if (["en", "en-us", "en-gb"].includes(text)) return "en";
  if (text === "ja") return "ja";
  if (text === "de") return "de";
  if (["pt", "pt-br"].includes(text)) return "pt-BR";
  if (text === "ko") return "ko";
  return "";
}

function targetLocaleList(value) {
  const seen = new Set();
  const out = [];
  for (const item of parseCommaList(value)) {
    const locale = normalizeLocaleTag(item);
    if (locale && locale !== sourceLocale && !seen.has(locale)) {
      seen.add(locale);
      out.push(locale);
    }
  }
  return out;
}

function localMapFromText(zh, en) {
  const out = {};
  const zhLines = lines(zh);
  const enLines = lines(en);
  if (zhLines.length) out.zh = zhLines;
  if (enLines.length) out.en = enLines;
  return out;
}

function setDirty(value = true) {
  state.dirty = value;
  $("dirtyBadge").classList.toggle("hidden", !value);
}

function messageTitle(tone) {
  if (tone === "ok") return "操作完成";
  if (tone === "error") return "操作失败";
  return "提示";
}

function showMessage(message, tone = "") {
  window.clearTimeout(showMessage.timer);
  const modal = $("messageModal");
  const card = modal?.querySelector(".modal-card");
  const title = $("messageModalTitle");
  const body = $("messageModalBody");
  if (!modal || !card || !title || !body) {
    window.alert(String(message ?? ""));
    return;
  }
  title.textContent = messageTitle(tone);
  body.textContent = String(message ?? "");
  card.className = `modal-card ${tone}`.trim();
  modal.classList.remove("hidden");
  modal.querySelector(".modal-actions [data-close-message-modal]")?.focus();
}

function closeMessageModal() {
  $("messageModal")?.classList.add("hidden");
}

function confirmDiscard() {
  if (!state.dirty) return true;
  return window.confirm("放弃未保存的更改吗？");
}

async function api(path, body) {
  const options = body === undefined
    ? {}
    : {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      };
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) {
    let message = typeof payload.error === "string" ? payload.error : "请求失败";
    if (response.status === 404 && String(path).startsWith("/api/git/")) {
      message = "Git 提交接口不存在，请重启本地配置管理器服务后刷新页面。";
    }
    const error = new Error(message);
    error.status = response.status;
    error.payload = payload.error;
    throw error;
  }
  return payload.data;
}

function fillSelect(id, values) {
  const select = $(id);
  select.innerHTML = values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(optionLabels[value] || localeLabels[value] || value)}</option>`).join("");
}

function setSelectOptions(id, options, selectedValue = "") {
  const select = $(id);
  const normalized = options.map((option) => (
    typeof option === "string" ? { value: option, label: option } : option
  ));
  const selected = String(selectedValue ?? "");
  if (selected && !normalized.some((option) => String(option.value) === selected)) {
    normalized.push({ value: selected, label: `当前值：${selected}` });
  }
  select.innerHTML = normalized
    .map((option) => `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`)
    .join("");
  select.value = selected;
}

function setVersionBoundarySelect(id, value) {
  setSelectOptions(id, versionBoundaryOptions(), String(value || "").trim());
}

function setMultiSelectOptions(id, options, selectedValues = []) {
  const root = $(id);
  const selected = new Set((selectedValues || []).map(String));
  const normalized = options.map((option) => (
    typeof option === "string" ? { value: option, label: option } : option
  ));
  for (const value of selected) {
    if (value && !normalized.some((option) => String(option.value) === value)) {
      normalized.push({ value, label: `未在 donors.json 中找到：${value}` });
    }
  }
  root.innerHTML = normalized.length
    ? normalized
      .map((option) => {
        const value = String(option.value);
        const label = String(option.label || value);
        return `<label class="dropdown-option">
          <input
            type="checkbox"
            value="${escapeHtml(value)}"
            data-multi-choice
            data-choice-label="${escapeHtml(label)}"
            ${selected.has(value) ? "checked" : ""}
          />
          <span>${escapeHtml(label)}</span>
        </label>`;
      })
      .join("")
    : `<div class="empty-state">暂无可选捐赠者。</div>`;
  updateMultiSelectSummary(id);
}

function updateMultiSelectSummary(id) {
  const root = $(id);
  const summary = $(`${id}Summary`);
  if (!root || !summary) return;
  const checked = Array.from(root.querySelectorAll("[data-multi-choice]:checked"));
  if (!checked.length) {
    summary.textContent = "未选择捐赠者";
    return;
  }
  const labels = checked.map((input) => input.dataset.choiceLabel || input.value);
  summary.textContent = labels.length <= 3
    ? labels.join("、")
    : `${labels.slice(0, 3).join("、")} 等 ${labels.length} 位`;
}

function displayOption(value) {
  return optionLabels[value] || value || "";
}

function displayLocale(value) {
  return localeLabels[value] || value || "";
}

function announcementCategoryLabel(value) {
  return announcementCategoryOptions.find((item) => item.value === value)?.label || value || "未分类";
}

function summaryLength(value) {
  return String(value || "").replace(/\s+/g, "").length;
}

function updateAnnouncementSummaryCount() {
  const counter = $("annSummaryCount");
  if (!counter) return;
  const count = summaryLength($("annSummaryZh")?.value || "");
  counter.textContent = `${count} / 50`;
  counter.classList.toggle("warn", count > 50);
}

function donorOptions() {
  return (state.data?.donors || [])
    .filter((donor) => donor && (donor.id || donor.name))
    .map((donor) => {
      const id = String(donor.id || "").trim();
      const name = String(donor.name || "").trim();
      return {
        value: id,
        label: name && id ? `${name} (${id})` : name || id,
      };
    })
    .filter((option) => option.value);
}

function setupSelects() {
  fillSelect("noticeStatus", statusOptions);
  fillSelect("noticeSeverity", severityOptions);
  fillSelect("noticeSurface", surfaceOptions);
  fillSelect("noticeDismiss", dismissOptions);
  fillSelect("updateStatus", statusOptions);
  fillSelect("updatePlatform", platformOptions);
  fillSelect("updateChannel", channelOptions);
  setSelectOptions("updatePriority", updatePriorityOptions, "0");
  fillSelect("localizedLocale", localizedAnnouncementLocales);
  fillSelect("localizedStatus", translationStatusOptions);
}

async function loadConfig() {
  const data = await api("/api/config");
  state.data = data;
  state.selectedAnnouncementId ||= data.currentAnnouncement?.id || data.history?.[0]?.id || "";
  state.selectedHistoryId ||= data.currentAnnouncement?.id || data.history?.[0]?.id || "";
  if (!(data.history || []).some((item) => String(item.id) === String(state.selectedAnnouncementId))) {
    state.selectedAnnouncementId = data.currentAnnouncement?.id || data.history?.[0]?.id || "";
  }
  if (!(data.history || []).some((item) => String(item.id) === String(state.selectedHistoryId))) {
    state.selectedHistoryId = data.currentAnnouncement?.id || data.history?.[0]?.id || "";
  }
  if (!state.selectedLocalizationAnnouncementId) {
    state.selectedLocalizationAnnouncementId = data.currentAnnouncement?.id || data.history?.[0]?.id || "";
  }
  if (!(data.announcements || []).some((item) => String(item.id) === String(state.selectedLocalizationAnnouncementId))) {
    state.selectedLocalizationAnnouncementId = data.currentAnnouncement?.id || data.history?.[0]?.id || "";
  }
  state.selectedNotice = Math.min(state.selectedNotice, Math.max((data.manifest.notices || []).length - 1, 0));
  state.selectedUpdate = Math.min(state.selectedUpdate, Math.max((data.manifest.updates || []).length - 1, 0));
  state.selectedDonor = Math.min(state.selectedDonor, Math.max((data.donors || []).length - 1, 0));
  $("repoRoot").textContent = data.repoRoot;
  renderAll();
  setDirty(false);
  loadGitSelectors({ applyDefault: true }).catch((error) => {
    console.warn(error);
    const box = $("commitRangeSummary");
    if (box) box.textContent = `无法读取 Git 范围：${error.message}`;
  });
}

function renderAll() {
  renderAnnouncementLoader();
  renderAnnouncementForm(selectedAnnouncementForEditor() || {});
  renderAnnouncementPreview();
  renderGitDefaults();
  renderHistoryList();
  renderHistoryPreview();
  renderLocalizationPanel();
  renderNoticeList();
  renderNoticeForm();
  renderNoticePreview();
  renderUpdateList();
  renderUpdateForm();
  renderUpdatePreview();
  renderDonorList();
  renderDonorForm();
  renderDonorPreview();
  renderOps();
}

function renderGitDefaults() {
  const defaults = state.data.gitDefaults || {};
  if ($("commitRepoPath") && !$("commitRepoPath").value) $("commitRepoPath").value = defaults.repoPath || "";
  if ($("commitFromRef") && !$("commitFromRef").value) $("commitFromRef").value = defaults.fromRef || "";
  if ($("commitToRef") && !$("commitToRef").value) $("commitToRef").value = defaults.toRef || "HEAD";
  if ($("commitLimit") && !$("commitLimit").value) $("commitLimit").value = "80";
  renderCommitRangeSelect();
  renderCommitSelects();
  if ($("aiTargetLocales") && !$("aiTargetLocales").value) $("aiTargetLocales").value = localizedAnnouncementLocales.join(", ");
}

function commitMatchesRef(commit, ref) {
  const text = String(ref || "").trim();
  if (!text || !commit) return false;
  const refs = String(commit.refs || "")
    .split(",")
    .map((item) => item.trim())
    .flatMap((item) => {
      const withoutTag = item.replace(/^tag:\s*/, "");
      const withoutHead = item.replace(/^HEAD\s*->\s*/, "");
      return [item, withoutTag, withoutHead];
    });
  return commit.hash === text
    || commit.short === text
    || commit.hash.startsWith(text)
    || refs.includes(text);
}

function commitForRef(ref) {
  return (state.commitChoices || []).find((commit) => commitMatchesRef(commit, ref)) || null;
}

function commitOptionLabel(commit) {
  const refs = commit.refs ? ` · ${commit.refs}` : "";
  return `${commit.short} · ${commit.date || ""} · ${commit.subject || ""}${refs}`;
}

function commitLabelForRef(ref) {
  const commit = commitForRef(ref);
  if (!commit) return ref || "";
  return `${commit.short} · ${commit.subject || ""}`;
}

function renderCommitSelects() {
  const fromSelect = $("commitFromSelect");
  const toSelect = $("commitToSelect");
  if (!fromSelect || !toSelect) return;
  const commits = state.commitChoices || [];
  const render = (select, currentRef, label) => {
    const matched = commitForRef(currentRef);
    select.innerHTML = [
      commits.length
        ? `<option value="__manual__">${escapeHtml(label)}：${escapeHtml(commitLabelForRef(currentRef) || "未选择")}</option>`
        : `<option value="__manual__">正在加载提交列表...</option>`,
      ...commits.map((commit) => `<option value="${escapeHtml(commit.hash)}">${escapeHtml(commitOptionLabel(commit))}</option>`),
    ].join("");
    select.value = matched ? matched.hash : "__manual__";
  };
  render(fromSelect, $("commitFromRef")?.value.trim(), "使用当前起点");
  render(toSelect, $("commitToRef")?.value.trim(), "使用当前终点");
}

function selectedCommitRangeOption() {
  const selected = $("commitRangePreset")?.value || state.selectedCommitRange || "";
  return (state.commitRanges || []).find((option) => String(option.value) === String(selected)) || null;
}

function renderCommitRangeSelect() {
  const select = $("commitRangePreset");
  if (!select) return;
  const ranges = state.commitRanges || [];
  const selected = state.selectedCommitRange || ranges[0]?.value || "__custom__";
  select.innerHTML = [
    `<option value="__custom__">自定义范围</option>`,
    ...ranges.map((option) => {
      const meta = option.range && option.limit ? ` · ${option.range} · ${option.limit}` : "";
      return `<option value="${escapeHtml(option.value)}">${escapeHtml(option.label || option.value)}${escapeHtml(meta)}</option>`;
    }),
  ].join("");
  select.value = ranges.some((option) => String(option.value) === String(selected)) ? selected : "__custom__";
  state.selectedCommitRange = select.value;
  renderCommitRangeSummary();
}

function renderCommitRangeSummary() {
  const box = $("commitRangeSummary");
  if (!box) return;
  const option = selectedCommitRangeOption();
  if (!option) {
    const fromRef = $("commitFromRef")?.value.trim() || "";
    const toRef = $("commitToRef")?.value.trim() || "HEAD";
    const range = fromRef ? `${commitLabelForRef(fromRef)} -> ${commitLabelForRef(toRef) || toRef}` : commitLabelForRef(toRef) || toRef;
    box.innerHTML = `
      <strong>${escapeHtml(range)}</strong>
      <span>当前使用自定义提交范围。</span>
      <span>已加载 ${escapeHtml((state.commitChoices || []).length)} 条提交可选。</span>
    `;
    return;
  }
  box.innerHTML = `
    <strong>${escapeHtml(option.range || option.value)}</strong>
    <span>最多读取 ${escapeHtml(option.limit || 80)} 条提交。</span>
    <span>已加载 ${escapeHtml((state.commitChoices || []).length)} 条提交可选。</span>
    ${option.description ? `<span>${escapeHtml(option.description)}</span>` : ""}
  `;
}

function applyCommitRangeOption(option) {
  if (!option) return;
  $("commitFromRef").value = option.fromRef || "";
  $("commitToRef").value = option.toRef || "HEAD";
  $("commitLimit").value = option.limit || 80;
  state.selectedCommitRange = option.value || "__custom__";
  renderCommitRangeSelect();
  renderCommitSelects();
}

async function loadCommitRanges({ applyDefault = false } = {}) {
  if (!$("commitRangePreset")) return null;
  const repoPath = $("commitRepoPath")?.value.trim() || state.data?.gitDefaults?.repoPath || "";
  const params = new URLSearchParams();
  if (repoPath) params.set("repoPath", repoPath);
  const data = await api(`/api/git/commit-ranges?${params.toString()}`);
  state.commitRanges = data.options || [];
  if ($("commitRepoPath") && data.repoPath) $("commitRepoPath").value = data.repoPath;
  if (applyDefault || !selectedCommitRangeOption()) {
    const option = state.commitRanges.find((item) => item.value === data.defaultValue) || state.commitRanges[0];
    if (option) applyCommitRangeOption(option);
  } else {
    renderCommitRangeSelect();
  }
  return data;
}

async function loadCommitChoices({ all = true } = {}) {
  if (!$("commitFromSelect") || !$("commitToSelect")) return null;
  const repoPath = $("commitRepoPath")?.value.trim() || state.data?.gitDefaults?.repoPath || "";
  const params = new URLSearchParams({ limit: all ? "all" : "500" });
  if (repoPath) params.set("repoPath", repoPath);
  const data = await api(`/api/git/commits?${params.toString()}`);
  state.commitChoices = data.commits || [];
  if ($("commitRepoPath") && data.repoPath) $("commitRepoPath").value = data.repoPath;
  renderCommitSelects();
  renderCommitRangeSummary();
  return data;
}

async function loadGitSelectors(options = {}) {
  let rangeError = null;
  try {
    await loadCommitRanges(options);
  } catch (error) {
    rangeError = error;
    state.commitRanges = [];
    renderCommitRangeSelect();
  }
  try {
    await loadCommitChoices({ all: true });
  } catch (error) {
    if (rangeError) throw rangeError;
    throw error;
  }
  if (rangeError) {
    const box = $("commitRangeSummary");
    if (box) {
      box.innerHTML = `
        <strong>已加载 ${escapeHtml((state.commitChoices || []).length)} 条提交。</strong>
        <span>范围预设读取失败：${escapeHtml(rangeError.message)}</span>
      `;
    }
  }
}

function applyCommitSelect(kind, value) {
  if (value === "__manual__") return;
  const commit = (state.commitChoices || []).find((item) => item.hash === value);
  if (!commit) return;
  if (kind === "from") {
    $("commitFromRef").value = commit.hash;
  } else {
    $("commitToRef").value = commit.hash;
  }
  state.selectedCommitRange = "__custom__";
  if ($("commitRangePreset")) $("commitRangePreset").value = "__custom__";
  renderCommitSelects();
  renderCommitRangeSummary();
}

function selectedAnnouncementForEditor() {
  if (state.selectedAnnouncementId === "__new__") return null;
  return (state.data.history || []).find((item) => String(item.id) === String(state.selectedAnnouncementId))
    || state.data.currentAnnouncement
    || state.data.history?.[0]
    || null;
}

function renderAnnouncementLoader() {
  const select = $("announcementLoader");
  if (!select) return;
  const items = state.data.history || [];
  select.innerHTML = items
    .map((item) => {
      const isLatest = String(item.id) === String(state.data.manifest?.latest_announcement_id || "");
      const label = `${isLatest ? "最新 / " : ""}${item.version || item.title || item.id} / ${item.date || ""} / ${item.id}`;
      return `<option value="${escapeHtml(item.id)}"${String(item.id) === String(state.selectedAnnouncementId) ? " selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("");
  const selected = selectedAnnouncementForEditor();
  $("announcementLoadSummary").textContent = selected
    ? `当前编辑：${selected.version || selected.title || selected.id} / ${selected.id}`
    : state.selectedAnnouncementId === "__new__"
      ? "当前编辑：新公告草稿，保存后会写入 update/announcements。"
    : "当前目录没有可加载的公告。";
}

function currentAnnouncementFromForm() {
  const summaryZh = lines($("annSummaryZh").value);
  return {
    id: $("annId").value.trim(),
    release_tag: $("annReleaseTag").value.trim(),
    version: $("annVersion").value.trim(),
    date: $("annDate").value.trim(),
    title: $("annTitle").value.trim(),
    show_when_up_to_date: $("annShowWhenUpToDate").checked,
    contents: summaryZh.length ? { zh: summaryZh } : {},
    new_donor_ids: selectedValues("annNewDonors"),
    items: announcementItemsFromEditor(),
  };
}

function todayDateString() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
}

function emptyAnnouncementTemplate() {
  return {
    id: "",
    release_tag: "",
    version: "",
    date: todayDateString(),
    title: "版本更新公告",
    show_when_up_to_date: false,
    contents: { zh: [] },
    new_donor_ids: [],
    items: [
      { category: "feature", contents: { zh: [] } },
      { category: "improvement", contents: { zh: [] } },
      { category: "fix", contents: { zh: [] } },
    ],
  };
}

function normalizeAnnouncementItems(items) {
  if (!Array.isArray(items)) return [];
  return items
    .filter((item) => item && typeof item === "object")
    .map((item) => {
      const zh = lines(item.contents?.zh);
      const fallback = zh.length ? [] : lines(item.contents?.en);
      return {
        category: String(item.category || "improvement").trim() || "improvement",
        contents: {
          zh: [...zh, ...fallback],
        },
      };
    });
}

function announcementCategorySelect(category) {
  const knownValues = announcementCategoryOptions.map((item) => item.value);
  const options = [...announcementCategoryOptions];
  if (category && !knownValues.includes(category)) {
    options.push({ value: category, label: category });
  }
  return `<select data-ann-item-category>${options
    .map((item) => `<option value="${escapeHtml(item.value)}"${item.value === category ? " selected" : ""}>${escapeHtml(item.label)}</option>`)
    .join("")}</select>`;
}

function renderAnnouncementLineInputs(groupIndex, lang, values) {
  const rows = values.length ? values : [""];
  const label = "中文内容";
  const placeholder = "输入一条中文更新内容";
  return rows
    .map(
      (value, lineIndex) => `
        <div class="item-line">
          <input
            data-ann-line-lang="${lang}"
            data-ann-line-index="${lineIndex}"
            value="${escapeHtml(value)}"
            placeholder="${escapeHtml(placeholder)}"
            aria-label="${escapeHtml(label)}"
          />
          <button type="button" class="danger compact" data-delete-ann-line="${lang}" data-line-index="${lineIndex}">删除</button>
        </div>
      `,
    )
    .join("");
}

function renderAnnouncementItems(items) {
  const normalized = normalizeAnnouncementItems(items);
  const editor = $("annItemsEditor");
  if (!normalized.length) {
    editor.innerHTML = `<div class="empty-state">暂无更新内容分组。点击右上角添加新增、优化或修复类型。</div>`;
    return;
  }
  editor.innerHTML = normalized
    .map(
      (item, groupIndex) => `
        <article class="item-group" data-ann-item-index="${groupIndex}">
          <div class="item-group-head">
            <button
              type="button"
              class="secondary compact drag-handle"
              draggable="true"
              data-ann-drag-handle
              aria-label="&#25302;&#21160;&#35843;&#25972;&#39034;&#24207;"
              title="&#25302;&#21160;&#35843;&#25972;&#39034;&#24207;"
            >&#8597;</button>
            <div>
              <span class="field-caption">类型</span>
              ${announcementCategorySelect(item.category)}
            </div>
            <div class="inline-actions">
              <button type="button" class="secondary compact" data-add-ann-line="zh">添加中文内容</button>
              <button type="button" class="danger compact" data-delete-ann-group>删除类型</button>
            </div>
          </div>
          <div>
            <span class="field-caption">中文</span>
            <div class="item-lines">${renderAnnouncementLineInputs(groupIndex, "zh", item.contents.zh)}</div>
          </div>
        </article>
      `,
    )
    .join("");
}

function announcementItemsFromEditor() {
  return Array.from(document.querySelectorAll("#annItemsEditor [data-ann-item-index]")).map((group) => {
    const category = group.querySelector("[data-ann-item-category]")?.value || "improvement";
    const contents = {};
    for (const lang of ["zh"]) {
      const values = Array.from(group.querySelectorAll(`[data-ann-line-lang="${lang}"]`))
        .map((input) => input.value.trim())
        .filter(Boolean);
      if (values.length) contents[lang] = values;
    }
    return { category, contents };
  });
}

function renderAnnouncementForm(announcement) {
  $("annId").value = announcement.id || "";
  $("annReleaseTag").value = announcement.release_tag || "";
  $("annVersion").value = announcement.version || "";
  $("annDate").value = announcement.date || "";
  $("annTitle").value = announcement.title || "";
  $("annShowWhenUpToDate").checked = Boolean(announcement.show_when_up_to_date);
  $("annSummaryZh").value = textFromLines(announcement.contents?.zh);
  setMultiSelectOptions("annNewDonors", donorOptions(), announcement.new_donor_ids || []);
  renderAnnouncementItems(announcement.items || []);
  updateAnnouncementSummaryCount();
}

function renderAnnouncementItemsPreview(items) {
  const visibleItems = normalizeAnnouncementItems(items).filter(
    (item) => item.contents.zh.length,
  );
  if (!visibleItems.length) return "";
  return `<div class="preview-items">${visibleItems
    .map(
      (item) => `
        <section>
          <strong>${escapeHtml(announcementCategoryLabel(item.category))}</strong>
          ${item.contents.zh.length ? `<ul>${item.contents.zh.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>` : ""}
        </section>
      `,
    )
    .join("")}</div>`;
}

function renderAnnouncementPreview() {
  updateAnnouncementSummaryCount();
  let ann;
  try {
    ann = currentAnnouncementFromForm();
  } catch {
    ann = state.data?.currentAnnouncement || {};
  }
  const zh = lines(ann.contents?.zh);
  const items = Array.isArray(ann.items) ? ann.items : [];
  $("announcementPreview").innerHTML = `
    <article class="preview-card">
      <h4>${escapeHtml(ann.title || "更新日志")} ${ann.version ? `v${escapeHtml(ann.version)}` : ""}</h4>
      ${zh.map((line) => `<p>${escapeHtml(line)}</p>`).join("")}
      <div class="pill-row">
        <span class="pill">id ${escapeHtml(ann.id || "新建")}</span>
        <span class="pill">${escapeHtml(ann.date || "无日期")}</span>
        <span class="pill">${items.length} 个更新分组</span>
        <span class="pill">${ann.show_when_up_to_date ? "当前版本也展示" : "仅更新时展示"}</span>
      </div>
      ${renderAnnouncementItemsPreview(items)}
    </article>
  `;
}

function renderHistoryList() {
  const items = state.data.history || [];
  const latestId = String(state.data.manifest?.latest_announcement_id || "");
  $("historyList").innerHTML = items
    .map((item) => {
      const isLatest = String(item.id) === latestId;
      const active = String(item.id) === String(state.selectedHistoryId) ? " active" : "";
      const latest = isLatest ? " latest" : "";
      return `<button class="list-item${active}${latest}" data-history-id="${escapeHtml(item.id)}">
        <strong>${escapeHtml(item.version || item.title || item.id)}${isLatest ? ` <span class="inline-badge">最新</span>` : ""}</strong>
        <span>${escapeHtml(item.date || "")} / ${escapeHtml(item.release_tag || "")} / id ${escapeHtml(item.id)}</span>
      </button>`;
    })
    .join("");
}

function selectedHistory() {
  return (state.data.history || []).find((item) => String(item.id) === String(state.selectedHistoryId)) || state.data.history?.[0];
}

function renderHistoryPreview() {
  const item = selectedHistory();
  if (!item) {
    $("historyPreview").innerHTML = `<p>暂无历史更新公告。</p>`;
    return;
  }
  const contents = item.contents || {};
  $("historyPreview").innerHTML = `
    <article class="preview-card">
      <h4>${escapeHtml(item.title || item.version || item.id)}</h4>
      <p>${escapeHtml(item.version || "")} ${escapeHtml(item.date || "")}</p>
      ${(contents.zh || []).map((line) => `<p>${escapeHtml(line)}</p>`).join("")}
      <div class="pill-row">
        <span class="pill">id ${escapeHtml(item.id)}</span>
        ${String(item.id) === String(state.data.manifest?.latest_announcement_id || "") ? `<span class="pill ok">当前最新公告</span>` : ""}
        <span class="pill">${(item.items || []).length} 个分组</span>
        <span class="pill">${(item.new_donor_ids || []).length} 位新增捐赠者</span>
      </div>
    </article>
  `;
}

function selectedLocalizationAnnouncement() {
  return (state.data.announcements || []).find(
    (item) => String(item.id) === String(state.selectedLocalizationAnnouncementId),
  ) || state.data.currentAnnouncement || state.data.history?.[0] || null;
}

function localizationStatusForSelected() {
  const id = selectedLocalizationAnnouncement()?.id || state.selectedLocalizationAnnouncementId;
  return state.data.localized?.announcements?.[id] || null;
}

function translationPillTone(status, stale) {
  if (status === "reviewed" && !stale) return "ok";
  if (status === "missing" || status === "stale" || stale) return "error";
  if (status === "source") return "ok";
  return "warn";
}

function renderAiSettings() {
  const settings = state.data.aiSettings || {};
  $("aiBaseUrl").value = settings.base_url || "";
  $("aiModel").value = settings.model || "";
  $("aiApiKey").value = "";
  $("aiClearApiKey").checked = false;
  $("aiSettingsSummary").innerHTML = `
    <div class="pill-row">
      <span class="pill ${settings.configured ? "ok" : "error"}">${settings.configured ? "API Key 已配置" : "缺少 API Key"}</span>
      <span class="pill">Key: ${escapeHtml(settings.api_key_source || "未配置")}</span>
      <span class="pill">Base: ${escapeHtml(settings.base_url_source || "default")}</span>
      <span class="pill">Model: ${escapeHtml(settings.model_source || "default")}</span>
    </div>
    <div class="refs">${escapeHtml(settings.settings_path || "config/ai.local.json")} 已被 .gitignore 忽略，仅本地使用。</div>
  `;
}

function renderLocalizationAnnouncementSelect() {
  const select = $("localizationAnnouncementId");
  const items = state.data.history || [];
  select.innerHTML = items
    .map((item) => {
      const label = `${item.version || item.title || item.id} / ${item.date || ""} / ${item.id}`;
      return `<option value="${escapeHtml(item.id)}"${String(item.id) === String(state.selectedLocalizationAnnouncementId) ? " selected" : ""}>${escapeHtml(label)}</option>`;
    })
    .join("");
  $("localizationTargetLocales").value ||= localizedAnnouncementLocales.join(", ");
}

function renderLocalizedCoverage() {
  const status = localizationStatusForSelected();
  if (!status) {
    $("localizedCoverageList").innerHTML = `<div class="empty-state">请选择一个更新公告。</div>`;
    return;
  }
  $("localizedCoverageList").innerHTML = allLocales
    .map((locale) => {
      const item = status.locales?.[locale] || { status: "missing", exists: false };
      const active = locale === state.selectedLocalizationLocale ? " active" : "";
      const tone = translationPillTone(item.status, item.stale);
      const detail = item.source
        ? "源公告文件"
        : item.exists
          ? `${item.summary_count || 0} 段摘要 / ${item.item_count || 0} 个分组`
          : "尚未生成";
      return `
        <button type="button" class="locale-card${active}" data-localized-locale="${escapeHtml(locale)}"${locale === sourceLocale ? " disabled" : ""}>
          <strong>${escapeHtml(displayLocale(locale))}</strong>
          <span class="pill ${tone}">${escapeHtml(displayOption(item.status))}</span>
          <small>${escapeHtml(detail)}</small>
          <small>${escapeHtml(item.path || "")}</small>
        </button>
      `;
    })
    .join("");
}

function normalizeLocalizedItems(items) {
  if (!Array.isArray(items)) return [];
  return items
    .filter((item) => item && typeof item === "object")
    .map((item) => ({
      category: String(item.category || "improvement").trim() || "improvement",
      contents: lines(item.contents),
    }));
}

function renderLocalizedItems(items, sourceItems = []) {
  const normalized = normalizeLocalizedItems(items);
  const sourceByCategory = new Map(
    sourceItems.map((item) => [item.category, lines(item.contents)]),
  );
  $("localizedItemsEditor").innerHTML = normalized.length
    ? normalized
        .map((item, index) => {
          const source = sourceByCategory.get(item.category) || [];
          return `
            <section class="localized-item" data-localized-item-index="${index}">
              <div class="item-group-head">
                <div>
                  <span class="field-caption">类型</span>
                  ${announcementCategorySelect(item.category).replace("data-ann-item-category", "data-localized-item-category")}
                </div>
                <span class="pill">${escapeHtml(source.length)} 条源内容</span>
              </div>
              <label>翻译内容 <textarea data-localized-item-contents rows="5">${escapeHtml(textFromLines(item.contents))}</textarea></label>
            </section>
          `;
        })
        .join("")
    : `<div class="empty-state">暂无分组。AI 生成后会按源公告分组写入。</div>`;
}

function renderLocalizedSourcePreview() {
  const payload = state.localizedEditor;
  if (!payload?.source) {
    $("localizedSourcePreview").innerHTML = `<div class="source-block">加载一个语言后会显示源中文内容。</div>`;
    return;
  }
  const source = payload.source;
  $("localizedSourcePreview").innerHTML = `
    <div class="source-block">
      <strong>源内容：${escapeHtml(source.title || source.id)}</strong>
      ${lines(source.summary).map((line) => `<p>${escapeHtml(line)}</p>`).join("")}
      ${(source.items || [])
        .map(
          (item) => `
            <div>
              <strong>${escapeHtml(announcementCategoryLabel(item.category))}</strong>
              <ul>${lines(item.contents).map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderLocalizedEditor() {
  const payload = state.localizedEditor;
  if (!payload?.announcement) {
    $("localizedLocale").value = state.selectedLocalizationLocale;
    $("localizedStatus").value = "needs_review";
    $("localizedTitle").value = "";
    $("localizedSummary").value = "";
    $("localizedItemsEditor").innerHTML = `<div class="empty-state">选择语言并加载翻译文件。</div>`;
    renderLocalizedSourcePreview();
    return;
  }
  const ann = payload.announcement;
  $("localizedLocale").value = ann.locale || state.selectedLocalizationLocale;
  $("localizedStatus").value = payload.stale ? "stale" : (payload.status || ann.translation?.status || "needs_review");
  $("localizedTitle").value = ann.title || "";
  $("localizedSummary").value = textFromLines(ann.summary || ann.contents);
  renderLocalizedItems(ann.items || [], payload.source?.items || []);
  renderLocalizedSourcePreview();
}

function renderLocalizationRunSummary() {
  const result = state.lastAiTranslation;
  if (!result) {
    $("localizationRunSummary").textContent = "默认只生成缺失、待审核或源内容已变更的翻译；已审核且未过期的文件会被跳过。";
    return;
  }
  const created = result.created || [];
  const skipped = result.skipped || [];
  $("localizationRunSummary").innerHTML = `
    <strong>本次生成 ${escapeHtml(created.length)} 个，跳过 ${escapeHtml(skipped.length)} 个。</strong>
    <div class="commit-list">
      ${created.map((item) => `<div><span class="pill ok">${escapeHtml(item.locale)}</span> ${escapeHtml(item.path)}</div>`).join("")}
      ${skipped.map((item) => `<div><span class="pill warn">${escapeHtml(item.locale)}</span> ${escapeHtml(item.reason)}</div>`).join("")}
    </div>
  `;
}

function renderLocalizationPanel() {
  renderAiSettings();
  renderLocalizationAnnouncementSelect();
  renderLocalizedCoverage();
  renderLocalizedEditor();
  renderLocalizationRunSummary();
}

function localizedAnnouncementFromEditor() {
  const items = Array.from(document.querySelectorAll("#localizedItemsEditor [data-localized-item-index]")).map((group) => ({
    category: group.querySelector("[data-localized-item-category]")?.value || "improvement",
    contents: lines(group.querySelector("[data-localized-item-contents]")?.value),
  }));
  return {
    id: state.selectedLocalizationAnnouncementId,
    locale: $("localizedLocale").value,
    title: $("localizedTitle").value.trim(),
    summary: lines($("localizedSummary").value),
    items,
    translation: {
      source_locale: sourceLocale,
      source_hash: state.localizedEditor?.source_hash || "",
      status: $("localizedStatus").value,
    },
  };
}

function noticeFromForm() {
  return {
    id: $("noticeId").value.trim(),
    revision: Number($("noticeRevision").value || 1),
    status: $("noticeStatus").value,
    priority: Number($("noticePriority").value || 0),
    severity: $("noticeSeverity").value,
    publish_at: $("noticePublishAt").value.trim(),
    expire_at: $("noticeExpireAt").value.trim(),
    audience: {
      platforms: checkedChoiceValues("noticePlatforms", "data-notice-platform"),
      channels: checkedChoiceValues("noticeChannels", "data-notice-channel"),
      min_app_version: $("noticeMinVersion").value.trim(),
      max_app_version: $("noticeMaxVersion").value.trim(),
    },
    display: {
      surface: $("noticeSurface").value,
      dismiss_policy: $("noticeDismiss").value,
      blocking: $("noticeBlocking").checked,
    },
    content: {
      title: {
        zh: $("noticeTitleZh").value.trim(),
        en: $("noticeTitleEn").value.trim(),
      },
      body: localMapFromText($("noticeBodyZh").value, $("noticeBodyEn").value),
    },
  };
}

function applyNoticeFormToState() {
  const notices = state.data.manifest.notices || [];
  if (!notices.length) return;
  notices[state.selectedNotice] = noticeFromForm();
  state.data.manifest.notices = notices;
}

function currentNotice() {
  return (state.data.manifest.notices || [])[state.selectedNotice] || null;
}

function renderNoticeList() {
  const notices = state.data.manifest.notices || [];
  $("noticeList").innerHTML = notices
    .map((notice, index) => {
      const active = index === state.selectedNotice ? " active" : "";
      return `<button class="list-item${active}" data-notice-index="${index}">
        <strong>${escapeHtml(notice.id || `notice-${index + 1}`)}</strong>
        <span>${escapeHtml(displayOption(notice.status || "draft"))} / 修订 ${escapeHtml(notice.revision || 1)}</span>
      </button>`;
    })
    .join("");
}

function renderNoticeForm() {
  const notice = currentNotice() || {};
  $("noticeId").value = notice.id || "";
  $("noticeRevision").value = notice.revision || 1;
  $("noticeStatus").value = notice.status || "draft";
  $("noticePriority").value = notice.priority || 0;
  $("noticeSeverity").value = notice.severity || "info";
  $("noticePublishAt").value = notice.publish_at || "";
  $("noticeExpireAt").value = notice.expire_at || "";
  renderNoticePublishDateTime($("noticePublishAt").value);
  setSelectOptions("noticeExpirePreset", noticeExpireOptions(notice), $("noticeExpireAt").value);
  $("noticeExpireAt").value = $("noticeExpirePreset").value;
  renderChoiceGroup(
    "noticePlatforms",
    "data-notice-platform",
    platformOptions,
    notice.audience?.platforms || [],
  );
  renderChoiceGroup(
    "noticeChannels",
    "data-notice-channel",
    channelOptions,
    notice.audience?.channels || [],
  );
  const minVersion = notice.audience?.min_app_version || "";
  const maxVersion = notice.audience?.max_app_version || "";
  setVersionBoundarySelect("noticeMinVersion", minVersion);
  setVersionBoundarySelect("noticeMaxVersion", maxVersion);
  $("noticeTestVersion").value = minVersion && minVersion === maxVersion ? minVersion : "";
  $("noticeSurface").value = notice.display?.surface || "startup_dialog";
  $("noticeDismiss").value = notice.display?.dismiss_policy || "once_per_revision";
  $("noticeBlocking").checked = Boolean(notice.display?.blocking);
  $("noticeLegacySync").checked = false;
  $("disableLegacyNotice").checked = false;
  $("noticeTitleZh").value = notice.content?.title?.zh || "";
  $("noticeTitleEn").value = notice.content?.title?.en || "";
  $("noticeBodyZh").value = textFromLines(notice.content?.body?.zh);
  $("noticeBodyEn").value = textFromLines(notice.content?.body?.en);
}

function renderNoticePreview() {
  const notice = noticeFromForm();
  const title = notice.content.title.zh || notice.content.title.en || notice.id || "通知";
  const body = notice.content.body.en || notice.content.body.zh || [];
  $("noticePreview").innerHTML = `
    <article class="preview-card">
      <h4>${escapeHtml(title)}</h4>
      ${body.map((line) => `<p>${escapeHtml(line)}</p>`).join("") || "<p>暂无正文内容。</p>"}
      <div class="pill-row">
        <span class="pill">${escapeHtml(displayOption(notice.status))}</span>
        <span class="pill">${escapeHtml(displayOption(notice.severity))}</span>
        <span class="pill">修订 ${escapeHtml(notice.revision)}</span>
        <span class="pill">${escapeHtml(displayOption(notice.display.dismiss_policy))}</span>
      </div>
    </article>
  `;
}

function uniqueUpdateVersions() {
  const seen = new Set();
  const out = [];
  for (const item of state.data.history || []) {
    const version = String(item.version || "").trim();
    if (version && !seen.has(version)) {
      seen.add(version);
      out.push({ value: version, label: `${version} / ${item.date || item.id}` });
    }
  }
  const versionInfo = state.data.manifest?.version_info || {};
  for (const info of Object.values(versionInfo)) {
    const version = String(info?.latest_version || "").trim();
    if (version && !seen.has(version)) {
      seen.add(version);
      out.push({ value: version, label: `${version} / 旧版 version_info` });
    }
  }
  return out;
}

function releaseNoteOptions() {
  return [
    { value: "", label: "不关联更新公告" },
    ...(state.data.history || []).map((item) => ({
      value: String(item.id || ""),
      label: `${item.version || item.title || item.id} / ${item.date || ""} / ${item.id}`,
    })),
  ];
}

function versionBoundaryOptions() {
  return [
    { value: "", label: "不限制" },
    ...uniqueUpdateVersions(),
  ];
}

function nowIsoString() {
  return new Date().toISOString();
}

function plusHoursIsoString(hours) {
  const date = new Date(Date.now() + hours * 60 * 60 * 1000);
  return date.toISOString();
}

function plusDaysIsoString(days) {
  const date = new Date(Date.now() + days * 24 * 60 * 60 * 1000);
  return date.toISOString();
}

function releaseNotePublishIso(releaseNoteId) {
  const item = (state.data.history || []).find((note) => String(note.id) === String(releaseNoteId));
  const date = String(item?.date || "").trim();
  return /^\d{4}-\d{2}-\d{2}$/.test(date) ? `${date}T00:00:00Z` : "";
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function localDateValue(date) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function localTimeValue(date) {
  return `${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function localDateTimePartsFromIso(value) {
  const text = String(value || "").trim();
  if (!text) return { date: "", time: "" };
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return { date: "", time: "" };
  return {
    date: localDateValue(date),
    time: localTimeValue(date),
  };
}

function parseClockTime(value) {
  const match = /^(\d{1,2}):(\d{2})$/.exec(String(value || "").trim());
  if (!match) return { hour: null, minute: null };
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (!Number.isInteger(hour) || hour < 0 || hour > 23) {
    return { hour: null, minute: null };
  }
  if (!Number.isInteger(minute) || minute < 0 || minute > 59) {
    return { hour: null, minute: null };
  }
  return { hour, minute };
}

function formatClockTime(hour, minute) {
  return `${pad2(hour)}:${pad2(minute)}`;
}

function clockValuesForMode(mode) {
  if (mode === "minute") {
    return Array.from({ length: 12 }, (_, index) => index * 5);
  }
  return Array.from({ length: 24 }, (_, index) => index);
}

function renderNoticeClock(timeValue = $("noticePublishTime").value) {
  const clock = $("noticePublishClock");
  const face = $("noticeClockFace");
  if (!clock || !face) return;
  const hasDate = Boolean($("noticePublishDate").value);
  const mode = clock.dataset.mode === "minute" ? "minute" : "hour";
  const parts = parseClockTime(timeValue);
  clock.classList.toggle("disabled", !hasDate);
  clock.setAttribute("aria-disabled", String(!hasDate));
  $("noticeClockHourMode").classList.toggle("active", mode === "hour");
  $("noticeClockMinuteMode").classList.toggle("active", mode === "minute");
  $("noticeClockHourMode").disabled = !hasDate;
  $("noticeClockMinuteMode").disabled = !hasDate;
  $("noticeClockHourMode").textContent = parts.hour == null ? "--" : pad2(parts.hour);
  $("noticeClockMinuteMode").textContent = parts.minute == null ? "--" : pad2(parts.minute);

  const values = clockValuesForMode(mode);
  const radius = mode === "hour" ? 104 : 94;
  face.innerHTML = values
    .map((value, index) => {
      const angle = (Math.PI * 2 * index) / values.length - Math.PI / 2;
      const x = Math.cos(angle) * radius;
      const y = Math.sin(angle) * radius;
      const selected = mode === "hour"
        ? parts.hour === value
        : parts.minute === value;
      return `<button type="button" data-clock-value="${value}" class="${selected ? "selected" : ""}" style="--clock-x: ${x.toFixed(2)}px; --clock-y: ${y.toFixed(2)}px;"${hasDate ? "" : " disabled"}>${pad2(value)}</button>`;
    })
    .join("");
}

function syncNoticePublishDateTime() {
  const dateValue = $("noticePublishDate").value;
  const timeInput = $("noticePublishTime");
  if (!dateValue) {
    timeInput.value = "";
    $("noticePublishAt").value = "";
    renderNoticeClock("");
    return;
  }
  const timeValue = timeInput.value;
  if (!timeValue) {
    $("noticePublishAt").value = "";
    return;
  }
  const localDateTime = new Date(`${dateValue}T${timeValue}:00`);
  $("noticePublishAt").value = Number.isNaN(localDateTime.getTime())
    ? ""
    : localDateTime.toISOString();
}

function renderNoticePublishDateTime(value) {
  const parts = localDateTimePartsFromIso(value);
  $("noticePublishDate").value = parts.date;
  $("noticePublishTime").value = parts.time;
  $("noticePublishClock").dataset.mode = "hour";
  renderNoticeClock(parts.time);
  syncNoticePublishDateTime();
}

function updateIdFromChoices(update) {
  const version = String(update.version || "").trim().replace(/^v/i, "");
  const parts = ["update", update.platform, update.channel, version || "unversioned"]
    .filter(Boolean)
    .join("-")
    .toLowerCase();
  return parts.replace(/[^a-z0-9._-]+/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
}

function checkedChoiceValues(containerId, dataAttribute) {
  return Array.from(document.querySelectorAll(`#${containerId} [${dataAttribute}]`))
    .filter((input) => input.checked)
    .map((input) => input.value);
}

function renderChoiceGroup(containerId, dataAttribute, values, selectedValues) {
  const selected = new Set((selectedValues || []).map((item) => String(item).toLowerCase()));
  $(containerId).innerHTML = values
    .map((value) => {
      const checked = selected.has(value) ? " checked" : "";
      return `<label><input type="checkbox" ${dataAttribute} value="${escapeHtml(value)}"${checked} />${escapeHtml(displayOption(value))}</label>`;
    })
    .join("");
}

function legacyVersionInfoForPlatform(platform) {
  return state.data.manifest?.version_info?.[platform] || null;
}

function updateUrlOptions(update) {
  const platform = update.platform || $("updatePlatform").value || "android";
  const currentUrl = String(update.download_url || update.url || "").trim();
  const legacyUrl = String(legacyVersionInfoForPlatform(platform)?.url || "").trim();
  const options = [{ value: "", label: "不设置下载地址" }];
  if (legacyUrl) {
    options.push({ value: legacyUrl, label: `使用 ${displayOption(platform)} 旧版配置地址` });
  }
  if (currentUrl && currentUrl !== legacyUrl) {
    options.push({ value: currentUrl, label: "保留当前候选地址" });
  }
  return options;
}

function updatePublishOptions(update) {
  const current = String(update.publish_at || "").trim();
  const releaseDate = releaseNotePublishIso($("updateReleaseNoteId")?.value || update.release_note_id);
  const options = [];
  if (current) options.push({ value: current, label: `保留当前值：${current}` });
  options.push({ value: nowIsoString(), label: "保存时立即生效" });
  if (releaseDate) options.push({ value: releaseDate, label: "使用关联公告日期 00:00 UTC" });
  options.push({ value: "", label: "不设置发布时间" });
  return options;
}

function updateExpireOptions(update) {
  const current = String(update.expire_at || "").trim();
  const options = [];
  if (current) options.push({ value: current, label: `保留当前值：${current}` });
  options.push({ value: "", label: "不过期" });
  options.push({ value: plusDaysIsoString(7), label: "7 天后过期" });
  options.push({ value: plusDaysIsoString(30), label: "30 天后过期" });
  return options;
}

function noticeExpireOptions(notice) {
  const current = String(notice.expire_at || "").trim();
  const options = [];
  if (current) options.push({ value: current, label: `保留当前值：${current}` });
  options.push({ value: "", label: "不过期" });
  options.push({ value: plusHoursIsoString(24), label: "24 小时后过期" });
  options.push({ value: plusDaysIsoString(7), label: "7 天后过期" });
  options.push({ value: plusDaysIsoString(30), label: "30 天后过期" });
  options.push({ value: plusDaysIsoString(45), label: "45 天后过期" });
  return options;
}

function syncUpdateDerivedFields() {
  const version = $("updateVersion").value;
  const platform = $("updatePlatform").value;
  const channel = $("updateChannel").value;
  const existingId = currentUpdate()?.id || "";
  const generatedId = updateIdFromChoices({ platform, channel, version });
  $("updateId").value = existingId || generatedId;

  const update = {
    platform,
    channel,
    version,
    download_url: $("updateUrl").value,
    release_note_id: $("updateReleaseNoteId").value,
    publish_at: $("updatePublishAt").value,
    expire_at: $("updateExpireAt").value,
  };
  const previousUrl = $("updateUrl").value;
  setSelectOptions("updateUrlPreset", updateUrlOptions(update), previousUrl);
  $("updateUrl").value = $("updateUrlPreset").value;

  const previousPublish = $("updatePublishAt").value;
  setSelectOptions("updatePublishPreset", updatePublishOptions(update), previousPublish);
  $("updatePublishAt").value = $("updatePublishPreset").value;

  const previousExpire = $("updateExpireAt").value;
  setSelectOptions("updateExpirePreset", updateExpireOptions(update), previousExpire);
  $("updateExpireAt").value = $("updateExpirePreset").value;
}

function updateFromForm() {
  const base = {
    platform: $("updatePlatform").value,
    channel: $("updateChannel").value,
    version: $("updateVersion").value.trim(),
  };
  return {
    id: $("updateId").value.trim() || updateIdFromChoices(base),
    status: $("updateStatus").value,
    priority: Number($("updatePriority").value || 0),
    platform: base.platform,
    channel: base.channel,
    version: base.version,
    force: $("updateForce").checked,
    download_url: $("updateUrl").value.trim(),
    release_note_id: $("updateReleaseNoteId").value.trim(),
    publish_at: $("updatePublishAt").value.trim(),
    expire_at: $("updateExpireAt").value.trim(),
    audience: {
      platforms: checkedChoiceValues("updateAudiencePlatforms", "data-update-audience-platform"),
      channels: checkedChoiceValues("updateAudienceChannels", "data-update-audience-channel"),
      min_app_version: $("updateMinVersion").value.trim(),
      max_app_version: $("updateMaxVersion").value.trim(),
    },
  };
}

function applyUpdateFormToState() {
  const updates = state.data.manifest.updates || [];
  if (!updates.length) return;
  updates[state.selectedUpdate] = updateFromForm();
  state.data.manifest.updates = updates;
}

function currentUpdate() {
  return (state.data.manifest.updates || [])[state.selectedUpdate] || null;
}

function renderUpdateList() {
  const updates = state.data.manifest.updates || [];
  $("updateList").innerHTML = updates
    .map((update, index) => {
      const active = index === state.selectedUpdate ? " active" : "";
      return `<button class="list-item${active}" data-update-index="${index}">
        <strong>${escapeHtml(update.id || `update-${index + 1}`)}</strong>
        <span>${escapeHtml(update.platform || "平台")} / ${escapeHtml(update.channel || "渠道")} / ${escapeHtml(update.version || "版本")}</span>
      </button>`;
    })
    .join("");
}

function renderUpdateForm() {
  const update = currentUpdate() || {};
  const versionOptions = uniqueUpdateVersions();
  const releaseOptions = releaseNoteOptions();
  const selectedReleaseNote = update.release_note_id || update.releaseNoteId || "";
  const selectedVersion = update.version || (
    (state.data.history || []).find((item) => String(item.id) === String(selectedReleaseNote))?.version || ""
  );
  $("updateId").value = update.id || updateIdFromChoices({
    platform: update.platform || "android",
    channel: update.channel || "full",
    version: selectedVersion,
  });
  $("updateStatus").value = update.status || "draft";
  setSelectOptions("updatePriority", updatePriorityOptions, String(update.priority ?? 0));
  $("updatePlatform").value = update.platform || "android";
  $("updateChannel").value = update.channel || "full";
  setSelectOptions("updateVersion", versionOptions, selectedVersion);
  $("updateForce").checked = Boolean(update.force);
  $("updateLegacySync").checked = false;
  setSelectOptions("updateReleaseNoteId", releaseOptions, selectedReleaseNote);
  $("updateUrl").value = update.download_url || update.url || "";
  setSelectOptions("updateUrlPreset", updateUrlOptions(update), $("updateUrl").value);
  $("updateUrl").value = $("updateUrlPreset").value;
  $("updatePublishAt").value = update.publish_at || "";
  setSelectOptions("updatePublishPreset", updatePublishOptions(update), $("updatePublishAt").value);
  $("updatePublishAt").value = $("updatePublishPreset").value;
  $("updateExpireAt").value = update.expire_at || "";
  setSelectOptions("updateExpirePreset", updateExpireOptions(update), $("updateExpireAt").value);
  $("updateExpireAt").value = $("updateExpirePreset").value;
  renderChoiceGroup(
    "updateAudiencePlatforms",
    "data-update-audience-platform",
    platformOptions,
    update.audience?.platforms || [],
  );
  renderChoiceGroup(
    "updateAudienceChannels",
    "data-update-audience-channel",
    channelOptions,
    update.audience?.channels || [],
  );
  setSelectOptions("updateMinVersion", versionBoundaryOptions(), update.audience?.min_app_version || "");
  setSelectOptions("updateMaxVersion", versionBoundaryOptions(), update.audience?.max_app_version || "");
}

function renderUpdatePreview() {
  const update = updateFromForm();
  const notes = (state.data.history || []).find((item) => item.version === update.release_note_id || item.id === update.release_note_id);
  $("updatePreview").innerHTML = `
    <article class="preview-card">
      <h4>${escapeHtml(update.version || "无版本")}</h4>
      <p>${escapeHtml(update.platform)} / ${escapeHtml(displayOption(update.channel))} / ${escapeHtml(displayOption(update.status))}</p>
      <p>${escapeHtml(update.download_url || "无下载地址")}</p>
      <div class="pill-row">
        <span class="pill">${update.force ? "强制更新" : "可选更新"}</span>
        <span class="pill">优先级 ${escapeHtml(update.priority)}</span>
        <span class="pill">${notes ? "已关联更新日志" : "未找到更新日志"}</span>
        <span class="pill">${escapeHtml(update.publish_at || "无发布时间")}</span>
      </div>
    </article>
  `;
}

function donorFromForm() {
  return {
    id: $("donorId").value.trim(),
    name: $("donorName").value.trim(),
    avatar: $("donorAvatar").value.trim(),
  };
}

function applyDonorFormToState() {
  const donors = state.data.donors || [];
  if (!donors.length) return;
  donors[state.selectedDonor] = donorFromForm();
  state.data.donors = donors;
}

function currentDonor() {
  return (state.data.donors || [])[state.selectedDonor] || null;
}

function renderDonorList() {
  const donors = state.data.donors || [];
  $("donorList").innerHTML = donors
    .map((donor, index) => {
      const active = index === state.selectedDonor ? " active" : "";
      return `<button class="list-item${active}" data-donor-index="${index}">
        <strong>${escapeHtml(donor.name || donor.id || `donor-${index + 1}`)}</strong>
        <span>${escapeHtml(donor.id || "")}</span>
      </button>`;
    })
    .join("");
}

function renderDonorForm() {
  const donor = currentDonor() || {};
  $("donorId").value = donor.id || "";
  $("donorName").value = donor.name || "";
  $("donorAvatar").value = donor.avatar || "";
  $("assetFile").value = "";
}

function renderDonorPreview() {
  const donor = donorFromForm();
  const refs = state.data.donorReferences?.[donor.id] || [];
  $("donorPreview").innerHTML = `
    <article class="preview-card">
      ${donor.avatar ? `<img class="donor-avatar" src="${escapeHtml(donor.avatar)}" alt="" />` : ""}
      <h4>${escapeHtml(donor.name || donor.id || "未选择捐赠者")}</h4>
      <p>${escapeHtml(donor.avatar || "无头像地址")}</p>
    </article>
  `;
  $("donorRefs").innerHTML = refs.length
    ? `<strong>被以下公告引用：</strong> ${refs.map((ref) => `${escapeHtml(ref.version || ref.announcement_id)} (${escapeHtml(ref.announcement_id)})`).join(", ")}`
    : "没有公告引用这个捐赠者 ID。";
}

function renderOps(commandResult) {
  const generated = state.data.generated || {};
  $("generatedSummary").innerHTML = [
    ["已生成 latest.json", generated.exists ? "是" : "否"],
    ["路径", generated.path || ""],
    ["更新日志数量", generated.release_notes_count ?? ""],
    ["捐赠者数量", generated.donors_count ?? ""],
    ["包含 v3 通知", generated.has_notices ? "是" : "否"],
    ["包含 v3 更新", generated.has_updates ? "是" : "否"],
    ["本地化输出", (generated.localized_outputs || []).join(", ")],
  ]
    .map(([label, value]) => `<div class="summary-row"><strong>${escapeHtml(label)}</strong><span>${escapeHtml(value)}</span></div>`)
    .join("");
  renderDiagnostics(state.data.diagnostics);
  if (commandResult) {
    $("commandOutput").textContent = [
      `命令：${commandResult.command || ""}`,
      `退出码：${commandResult.returncode}`,
      "",
      commandResult.stdout || "",
      commandResult.stderr || "",
    ].join("\n");
  }
}

function renderDiagnostics(diagnostics) {
  const errors = diagnostics?.errors || [];
  const warnings = diagnostics?.warnings || [];
  if (!errors.length && !warnings.length) {
    $("diagnostics").innerHTML = `<div class="diag">暂无 v3 诊断信息。</div>`;
    return;
  }
  $("diagnostics").innerHTML = [
    ...errors.map((message) => `<div class="diag error">${escapeHtml(message)}</div>`),
    ...warnings.map((message) => `<div class="diag warn">${escapeHtml(message)}</div>`),
  ].join("");
}

function switchPanel(panel) {
  if (panel !== state.panel && !confirmDiscard()) return;
  state.panel = panel;
  document.querySelectorAll(".nav button").forEach((button) => button.classList.toggle("active", button.dataset.panel === panel));
  document.querySelectorAll(".panel").forEach((section) => section.classList.toggle("active", section.id === `panel-${panel}`));
  $("panelTitle").textContent = {
    update: "更新公告",
    history: "历史公告",
    localization: "AI 翻译",
    notices: "通知公告",
    updates: "更新候选",
    donors: "捐赠者",
    ops: "校验与构建",
  }[panel];
  setDirty(false);
}

function updateAnnouncementItems(mutator) {
  const items = announcementItemsFromEditor();
  mutator(items);
  renderAnnouncementItems(items);
  renderAnnouncementPreview();
  setDirty(true);
}

function moveAnnouncementItemGroup(fromIndex, rawToIndex) {
  const items = announcementItemsFromEditor();
  const from = Number(fromIndex);
  let to = Number(rawToIndex);
  if (!Number.isInteger(from) || from < 0 || from >= items.length) return false;
  if (!Number.isInteger(to)) return false;
  to = Math.max(0, Math.min(items.length, to));
  if (from < to) to -= 1;
  if (from === to) return false;
  const [item] = items.splice(from, 1);
  items.splice(to, 0, item);
  renderAnnouncementItems(items);
  renderAnnouncementPreview();
  setDirty(true);
  return true;
}

function addAnnouncementItemGroup(category) {
  updateAnnouncementItems((items) => {
    items.push({ category, contents: { zh: [] } });
  });
}

function addAnnouncementItemLine(groupIndex, lang) {
  updateAnnouncementItems((items) => {
    const item = items[groupIndex];
    if (!item) return;
    item.contents = item.contents || {};
    item.contents[lang] = lines(item.contents[lang]);
    item.contents[lang].push("");
  });
}

function deleteAnnouncementItemGroup(groupIndex) {
  updateAnnouncementItems((items) => {
    items.splice(groupIndex, 1);
  });
}

function deleteAnnouncementItemLine(groupIndex, lang, lineIndex) {
  updateAnnouncementItems((items) => {
    const item = items[groupIndex];
    if (!item) return;
    item.contents = item.contents || {};
    item.contents[lang] = lines(item.contents[lang]);
    item.contents[lang].splice(lineIndex, 1);
  });
}

function announcementItemDropPosition(group, event) {
  const rect = group.getBoundingClientRect();
  return event.clientY > rect.top + rect.height / 2 ? "after" : "before";
}

function clearAnnouncementItemDropState() {
  document.querySelectorAll("#annItemsEditor .item-group.drop-before, #annItemsEditor .item-group.drop-after")
    .forEach((group) => {
      group.classList.remove("drop-before", "drop-after");
      delete group.dataset.dropPosition;
    });
}

function markAnnouncementItemDropTarget(group, position) {
  clearAnnouncementItemDropState();
  group.classList.add(`drop-${position}`);
  group.dataset.dropPosition = position;
}

function handleAnnouncementItemDragStart(event) {
  const handle = event.target.closest("[data-ann-drag-handle]");
  if (!handle) return;
  const group = handle.closest("[data-ann-item-index]");
  if (!group) return;
  const index = Number(group.dataset.annItemIndex);
  if (!Number.isInteger(index)) return;
  state.draggedAnnouncementItemIndex = index;
  group.classList.add("dragging");
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", String(index));
}

function handleAnnouncementItemDragOver(event) {
  if (state.draggedAnnouncementItemIndex === null) return;
  const group = event.target.closest("#annItemsEditor [data-ann-item-index]");
  if (!group) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "move";
  markAnnouncementItemDropTarget(group, announcementItemDropPosition(group, event));
}

function handleAnnouncementItemDrop(event) {
  if (state.draggedAnnouncementItemIndex === null) return;
  const group = event.target.closest("#annItemsEditor [data-ann-item-index]");
  if (!group) return;
  event.preventDefault();
  const targetIndex = Number(group.dataset.annItemIndex);
  const position = group.dataset.dropPosition || announcementItemDropPosition(group, event);
  const insertionIndex = targetIndex + (position === "after" ? 1 : 0);
  moveAnnouncementItemGroup(state.draggedAnnouncementItemIndex, insertionIndex);
  state.draggedAnnouncementItemIndex = null;
  clearAnnouncementItemDropState();
}

function handleAnnouncementItemDragEnd() {
  state.draggedAnnouncementItemIndex = null;
  clearAnnouncementItemDropState();
  document.querySelectorAll("#annItemsEditor .item-group.dragging")
    .forEach((group) => group.classList.remove("dragging"));
}

function handleAnnouncementItemKeydown(event) {
  const handle = event.target.closest("[data-ann-drag-handle]");
  if (!handle) return;
  const group = handle.closest("[data-ann-item-index]");
  if (!group) return;
  const index = Number(group.dataset.annItemIndex);
  if (event.key === "ArrowUp") {
    event.preventDefault();
    moveAnnouncementItemGroup(index, index - 1);
  } else if (event.key === "ArrowDown") {
    event.preventDefault();
    moveAnnouncementItemGroup(index, index + 2);
  }
}

function commitGenerationPayload() {
  return {
    repoPath: $("commitRepoPath").value.trim(),
    fromRef: $("commitFromRef").value.trim(),
    toRef: $("commitToRef").value.trim() || "HEAD",
    limit: Number($("commitLimit").value || 80),
  };
}

function mergeAnnouncementItems(existingItems, generatedItems) {
  const merged = normalizeAnnouncementItems(existingItems);
  for (const generated of normalizeAnnouncementItems(generatedItems)) {
    let target = merged.find((item) => item.category === generated.category);
    if (!target) {
      target = { category: generated.category, contents: { zh: [] } };
      merged.push(target);
    }
    for (const lang of ["zh"]) {
      const current = new Set(target.contents[lang] || []);
      for (const line of generated.contents[lang] || []) {
        if (!current.has(line)) {
          target.contents[lang].push(line);
          current.add(line);
        }
      }
    }
  }
  return merged;
}

function renderCommitGenerationSummary(result) {
  const commits = result.commits || [];
  if (!commits.length) {
    $("commitGenerateSummary").innerHTML = `范围 ${escapeHtml(result.range || "")} 内没有可生成的提交。`;
    return;
  }
  $("commitGenerateSummary").innerHTML = `
    <strong>${escapeHtml(result.range || "")}</strong> 读取到 ${escapeHtml(result.count)} 条提交，已生成 ${escapeHtml((result.items || []).length)} 个分组。
    <div class="commit-list">
      ${commits
        .slice(0, 24)
        .map(
          (commit) => `<div><span class="pill">${escapeHtml(announcementCategoryLabel(commit.category))}</span> <code>${escapeHtml(commit.short)}</code> ${escapeHtml(commit.text || commit.subject)}</div>`,
        )
        .join("")}
    </div>
  `;
}

function renderAiTranslationSummary(result) {
  const created = result?.aiTranslation?.created || [];
  const skipped = result?.aiTranslation?.skipped || [];
  if (!created.length && !skipped.length) {
    $("aiTranslateSummary").textContent = "没有生成翻译草稿。";
    return;
  }
  $("aiTranslateSummary").innerHTML = `
    <strong>已生成 ${escapeHtml(created.length)} 个翻译草稿，跳过 ${escapeHtml(skipped.length)} 个。</strong>
    <div class="commit-list">
      ${created
        .map((item) => `<div><span class="pill">${escapeHtml(item.locale)}</span> ${escapeHtml(item.path)}</div>`)
        .join("")}
      ${skipped
        .map((item) => `<div><span class="pill warn">${escapeHtml(item.locale)}</span> ${escapeHtml(item.reason)}</div>`)
        .join("")}
    </div>
  `;
}

async function generateAnnouncementItemsFromCommits() {
  const append = $("commitAppendMode").checked;
  const existingItems = announcementItemsFromEditor();
  const hasExistingContent = existingItems.some((item) => lines(item.contents?.zh).length || lines(item.contents?.en).length);
  if (!append && hasExistingContent && !window.confirm("生成结果会替换当前更新内容分组。继续吗？")) {
    return;
  }
  const result = await api("/api/announcement/generate-from-commits", commitGenerationPayload());
  $("commitRepoPath").value = result.repoPath || $("commitRepoPath").value;
  $("commitFromRef").value = result.fromRef || $("commitFromRef").value;
  $("commitToRef").value = result.toRef || $("commitToRef").value;
  const items = append ? mergeAnnouncementItems(existingItems, result.items || []) : result.items || [];
  renderAnnouncementItems(items);
  renderAnnouncementPreview();
  renderCommitGenerationSummary(result);
  setDirty(true);
  showMessage("已根据 Git 提交生成更新内容，请检查后再保存。", "ok");
}

async function generateAnnouncementSummary() {
  const announcement = currentAnnouncementFromForm();
  const hasItemContent = (announcement.items || []).some((item) => lines(item.contents?.zh).length);
  if (!announcement.title && !hasItemContent) {
    throw new Error("请先填写标题或更新内容，再生成摘要。");
  }
  if (!window.confirm("将调用本地 AI 服务生成 50 字以内中文摘要。继续吗？")) return;
  const result = await api("/api/announcement/ai-summary", { announcement });
  $("annSummaryZh").value = textFromLines(result.summary || []);
  renderAnnouncementPreview();
  setDirty(true);
  showMessage("AI 摘要已生成，请检查后再保存公告。", "ok");
}

async function generateAiTranslations() {
  const announcement = currentAnnouncementFromForm();
  if (!announcement.id) throw new Error("AI 翻译需要先保存或填写公告 ID。");
  const targetLocales = targetLocaleList($("aiTargetLocales").value || localizedAnnouncementLocales.join(", "));
  if (!targetLocales.length) throw new Error("请至少填写一个目标语言。");
  if (!window.confirm("将调用本地配置的 AI 服务，并写入 ai_draft 翻译文件。继续吗？")) {
    return;
  }
  const data = await api("/api/announcement/ai-translate", {
    announcement,
    target_locales: targetLocales,
    overwrite: false,
  });
  state.data = data;
  state.lastAiTranslation = data.aiTranslation || null;
  renderAll();
  renderAiTranslationSummary(data);
  setDirty(false);
  showMessage("AI 翻译草稿已生成。请人工审核后把翻译状态改为 reviewed。", "ok");
}

async function saveAiSettings() {
  const data = await api("/api/ai/settings/save", {
    base_url: $("aiBaseUrl").value.trim(),
    model: $("aiModel").value.trim(),
    api_key: $("aiApiKey").value.trim(),
    clear_api_key: $("aiClearApiKey").checked,
  });
  state.data = data;
  renderLocalizationPanel();
  showMessage("AI 本地设置已保存。", "ok");
}

async function generateLocalizationTranslations() {
  const announcement = selectedLocalizationAnnouncement();
  if (!announcement?.id) throw new Error("请先选择一个更新公告。");
  const targetLocales = targetLocaleList($("localizationTargetLocales").value || localizedAnnouncementLocales.join(", "));
  if (!targetLocales.length) throw new Error("请至少填写一个目标语言。");
  if (!window.confirm("将调用本地 AI 服务生成翻译草稿。继续吗？")) return;
  const data = await api("/api/announcement/ai-translate", {
    announcement,
    target_locales: targetLocales,
    overwrite: $("localizationOverwrite").checked,
  });
  state.data = data;
  state.lastAiTranslation = data.aiTranslation || null;
  state.localizedEditor = null;
  renderLocalizationPanel();
  setDirty(false);
  showMessage("AI 翻译任务完成，请在右侧审核后保存为 reviewed。", "ok");
}

async function loadLocalizedEditor() {
  const annId = $("localizationAnnouncementId").value || state.selectedLocalizationAnnouncementId;
  const locale = $("localizedLocale").value || state.selectedLocalizationLocale;
  if (!annId) throw new Error("请先选择一个更新公告。");
  if (locale === sourceLocale) throw new Error("源语言不需要加载翻译文件。");
  state.selectedLocalizationAnnouncementId = annId;
  state.selectedLocalizationLocale = locale;
  state.localizedEditor = await api(`/api/announcement/localized?id=${encodeURIComponent(annId)}&locale=${encodeURIComponent(locale)}`);
  renderLocalizedCoverage();
  renderLocalizedEditor();
  setDirty(false);
}

async function saveLocalizedAnnouncement() {
  const annId = state.selectedLocalizationAnnouncementId || $("localizationAnnouncementId").value;
  const locale = $("localizedLocale").value;
  if (!annId || !locale) throw new Error("请先加载一个翻译文件。");
  const data = await api("/api/announcement/localized/save", {
    announcement_id: annId,
    locale,
    status: $("localizedStatus").value,
    announcement: localizedAnnouncementFromEditor(),
  });
  state.data = data;
  state.localizedEditor = data.localizedEditor || null;
  renderLocalizationPanel();
  setDirty(false);
  showMessage("翻译文件已保存。", "ok");
}

async function deleteLocalizedAnnouncement() {
  const annId = state.selectedLocalizationAnnouncementId || $("localizationAnnouncementId").value;
  const locale = $("localizedLocale").value;
  if (!annId || !locale) throw new Error("请先选择要删除的翻译文件。");
  if (!window.confirm(`确认删除 ${annId} / ${locale} 的本地化文件吗？`)) return;
  const data = await api("/api/announcement/localized/delete", {
    announcement_id: annId,
    locale,
  });
  state.data = data;
  state.localizedEditor = null;
  renderLocalizationPanel();
  setDirty(false);
  showMessage("翻译文件已删除。", "ok");
}

async function saveAnnouncement() {
  const announcement = currentAnnouncementFromForm();
  const data = await api("/api/announcement/save", { announcement });
  const savedId = data.savedAnnouncementId || announcement.id;
  state.data = data;
  state.selectedAnnouncementId = savedId;
  state.selectedHistoryId = savedId;
  renderAll();
  setDirty(false);
  showMessage("更新公告已保存。", "ok");
}

function newAnnouncementDraft() {
  if (!confirmDiscard()) return;
  state.selectedAnnouncementId = "__new__";
  renderAnnouncementForm(emptyAnnouncementTemplate());
  renderAnnouncementPreview();
  renderAnnouncementLoader();
  renderHistoryList();
  setDirty(true);
  showMessage("已创建本地草稿。填写后点击“保存公告”写入配置文件。", "ok");
}

function loadAnnouncementForEdit() {
  if (!confirmDiscard()) return;
  const annId = $("announcementLoader").value;
  const announcement = (state.data.history || []).find((item) => String(item.id) === String(annId));
  if (!announcement) throw new Error("未找到选择的公告文件。");
  state.selectedAnnouncementId = announcement.id;
  state.selectedHistoryId = announcement.id;
  renderAnnouncementForm(announcement);
  renderAnnouncementPreview();
  renderAnnouncementLoader();
  renderHistoryList();
  setDirty(false);
  showMessage(`已加载公告 ${announcement.id}。`, "ok");
}

async function setSelectedHistoryAsLatest() {
  const item = selectedHistory();
  if (!item) throw new Error("请先选择一个历史公告。");
  if (String(item.id) === String(state.data.manifest?.latest_announcement_id || "")) {
    showMessage("该公告已经是最新公告。", "ok");
    return;
  }
  if (!window.confirm(`将 ${item.version || item.title || item.id} 设为最新公告吗？`)) return;
  const data = await api("/api/announcement/set-latest", { id: item.id });
  state.data = data;
  state.selectedHistoryId = item.id;
  state.selectedAnnouncementId = item.id;
  renderAll();
  setDirty(false);
  showMessage(`已将公告 ${item.id} 设为最新公告。`, "ok");
}

async function deleteAnnouncementById(id, label) {
  const annId = String(id || "").trim();
  if (!annId) throw new Error("请先选择要删除的更新公告。");
  if (!window.confirm(`确认删除${label} ${annId} 吗？\n\n该操作会移除源公告 JSON，并从 manifest 中解除引用。`)) {
    return;
  }
  const data = await api("/api/announcement/delete", { id: annId });
  state.data = data;
  state.selectedHistoryId = data.currentAnnouncement?.id || "";
  state.selectedAnnouncementId = data.currentAnnouncement?.id || data.history?.[0]?.id || "";
  renderAll();
  setDirty(false);
  showMessage(`已删除更新公告 ${annId}。`, "ok");
}

async function deleteCurrentAnnouncement() {
  if (state.dirty && !window.confirm("当前表单有未保存的更改。仍然删除这个公告文件吗？")) {
    return;
  }
  await deleteAnnouncementById($("annId").value, "当前公告");
}

async function deleteSelectedHistory() {
  const item = selectedHistory();
  if (!item) throw new Error("暂无可删除的历史更新公告。");
  await deleteAnnouncementById(item.id, "历史公告");
}

async function saveNotices() {
  applyNoticeFormToState();
  const current = currentNotice();
  const payload = { notices: state.data.manifest.notices || [] };
  if ($("noticeLegacySync").checked) {
    if (!current?.id) throw new Error("同步旧版 notice 需要通知 ID。");
    payload.legacy_notice_id = current.id;
  } else if ($("disableLegacyNotice").checked) {
    payload.legacy_notice_enabled = false;
  }
  const data = await api("/api/notices/save", payload);
  state.data = data;
  renderAll();
  setDirty(false);
  showMessage("通知公告已保存。", "ok");
}

async function saveUpdates() {
  applyUpdateFormToState();
  const current = currentUpdate();
  const payload = { updates: state.data.manifest.updates || [], legacy_syncs: [] };
  if ($("updateLegacySync").checked) {
    if (!current?.id) throw new Error("同步旧版 version_info 需要更新候选 ID。");
    payload.legacy_syncs.push({ id: current.id, platform: current.platform });
  }
  const data = await api("/api/updates/save", payload);
  state.data = data;
  renderAll();
  setDirty(false);
  showMessage("更新候选已保存。", "ok");
}

async function saveDonors(confirmReferencedDeletes = false) {
  applyDonorFormToState();
  try {
    const data = await api("/api/donors/save", {
      donors: state.data.donors || [],
      confirm_referenced_deletes: confirmReferencedDeletes,
    });
    state.data = data;
    renderAll();
    setDirty(false);
    showMessage("捐赠者已保存。", "ok");
  } catch (error) {
    if (error.status === 409 && error.payload?.referencedDonors) {
      const detail = Object.entries(error.payload.referencedDonors)
        .map(([id, refs]) => `${id}: ${refs.map((ref) => ref.announcement_id).join(", ")}`)
        .join("\n");
      if (window.confirm(`部分被删除的捐赠者仍被公告引用：\n${detail}\n\n仍然保存吗？`)) {
        await saveDonors(true);
      }
      return;
    }
    throw error;
  }
}

async function uploadAsset() {
  const file = $("assetFile").files?.[0];
  if (!file) throw new Error("请先选择头像文件。");
  const donor = donorFromForm();
  const data = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
  const result = await api("/api/assets/upload", {
    filename: file.name,
    path: file.name,
    name: donor.name || donor.id,
    donor_id: donor.id,
    auto_name: true,
    data,
  });
  $("donorAvatar").value = result.url;
  applyDonorFormToState();
  setDirty(true);
  renderDonorPreview();
  showMessage(`已上传 ${result.filename}。`, "ok");
}

async function runCommand(path) {
  const data = await api(path, {});
  renderOps(data);
  showMessage(data.ok ? "命令执行完成。" : "命令执行失败。", data.ok ? "ok" : "error");
  await loadConfig();
  switchPanel("ops");
  renderOps(data);
}

function addNotice() {
  state.data.manifest.notices = state.data.manifest.notices || [];
  state.data.manifest.notices.push({
    id: `notice-${new Date().toISOString().slice(0, 10)}`,
    revision: 1,
    status: "draft",
    priority: 0,
    severity: "info",
    audience: { platforms: [], channels: [], min_app_version: "", max_app_version: "" },
    display: { surface: "startup_dialog", dismiss_policy: "once_per_revision", blocking: false },
    content: { title: { zh: "", en: "" }, body: { zh: [], en: [] } },
  });
  state.selectedNotice = state.data.manifest.notices.length - 1;
  renderNoticeList();
  renderNoticeForm();
  renderNoticePreview();
  setDirty(true);
}

function deleteNotice() {
  const notices = state.data.manifest.notices || [];
  if (!notices.length) return;
  notices.splice(state.selectedNotice, 1);
  state.selectedNotice = Math.max(0, state.selectedNotice - 1);
  renderNoticeList();
  renderNoticeForm();
  renderNoticePreview();
  setDirty(true);
}

function addUpdate() {
  state.data.manifest.updates = state.data.manifest.updates || [];
  const latest = state.data.currentAnnouncement || state.data.history?.[0] || {};
  const platform = "android";
  const channel = "full";
  const version = latest.version || legacyVersionInfoForPlatform(platform)?.latest_version || "";
  state.data.manifest.updates.push({
    id: "",
    status: "draft",
    priority: 0,
    platform,
    channel,
    version,
    force: false,
    download_url: legacyVersionInfoForPlatform(platform)?.url || "",
    release_note_id: latest.id || "",
    publish_at: "",
    audience: { platforms: [], channels: [], min_app_version: "", max_app_version: "" },
  });
  state.selectedUpdate = state.data.manifest.updates.length - 1;
  renderUpdateList();
  renderUpdateForm();
  renderUpdatePreview();
  setDirty(true);
}

function deleteUpdate() {
  const updates = state.data.manifest.updates || [];
  if (!updates.length) return;
  updates.splice(state.selectedUpdate, 1);
  state.selectedUpdate = Math.max(0, state.selectedUpdate - 1);
  renderUpdateList();
  renderUpdateForm();
  renderUpdatePreview();
  setDirty(true);
}

function addDonor() {
  state.data.donors = state.data.donors || [];
  state.data.donors.push({ id: "", name: "", avatar: "" });
  state.selectedDonor = state.data.donors.length - 1;
  renderDonorList();
  renderDonorForm();
  renderDonorPreview();
  setDirty(true);
}

function deleteDonor() {
  const donors = state.data.donors || [];
  if (!donors.length) return;
  const donor = donors[state.selectedDonor];
  const refs = state.data.donorReferences?.[donor.id] || [];
  if (refs.length && !window.confirm(`捐赠者 ${donor.id} 被 ${refs.length} 条公告引用。仍然在本地删除吗？`)) {
    return;
  }
  donors.splice(state.selectedDonor, 1);
  state.selectedDonor = Math.max(0, state.selectedDonor - 1);
  renderDonorList();
  renderDonorForm();
  renderDonorPreview();
  setDirty(true);
}

function attachEvents() {
  document.querySelectorAll(".nav button").forEach((button) => {
    button.addEventListener("click", () => switchPanel(button.dataset.panel));
  });
  $("reloadBtn").addEventListener("click", () => {
    if (confirmDiscard()) loadConfig().catch(handleError);
  });
  $("messageModal").addEventListener("click", (event) => {
    if (!event.target.closest("[data-close-message-modal]")) return;
    closeMessageModal();
  });
  window.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("messageModal").classList.contains("hidden")) {
      closeMessageModal();
    }
  });
  document.querySelectorAll("[data-add-ann-group]").forEach((button) => {
    button.addEventListener("click", () => addAnnouncementItemGroup(button.dataset.addAnnGroup));
  });
  if ($("generateFromCommitsBtn")) {
    $("generateFromCommitsBtn").addEventListener("click", () => generateAnnouncementItemsFromCommits().catch(handleError));
  }
  if ($("generateSummaryBtn")) {
    $("generateSummaryBtn").addEventListener("click", () => generateAnnouncementSummary().catch(handleError));
  }
  if ($("refreshCommitRangesBtn")) {
    $("refreshCommitRangesBtn").addEventListener("click", () => loadGitSelectors({ applyDefault: true }).catch(handleError));
  }
  if ($("commitRangePreset")) {
    $("commitRangePreset").addEventListener("change", () => {
      const option = selectedCommitRangeOption();
      if (option) {
        applyCommitRangeOption(option);
      } else {
        state.selectedCommitRange = "__custom__";
        renderCommitRangeSummary();
      }
    });
  }
  if ($("commitFromSelect")) {
    $("commitFromSelect").addEventListener("change", () => applyCommitSelect("from", $("commitFromSelect").value));
  }
  if ($("commitToSelect")) {
    $("commitToSelect").addEventListener("change", () => applyCommitSelect("to", $("commitToSelect").value));
  }
  if ($("commitRepoPath")) {
    $("commitRepoPath").addEventListener("change", () => loadGitSelectors({ applyDefault: true }).catch(handleError));
  }
  ["commitFromRef", "commitToRef", "commitLimit"].forEach((id) => {
    if (!$(id)) return;
    $(id).addEventListener("input", () => {
      state.selectedCommitRange = "__custom__";
      if ($("commitRangePreset")) $("commitRangePreset").value = "__custom__";
      renderCommitSelects();
      renderCommitRangeSummary();
    });
  });
  if ($("aiTranslateBtn")) {
    $("aiTranslateBtn").addEventListener("click", () => generateAiTranslations().catch(handleError));
  }
  $("saveAiSettingsBtn").addEventListener("click", () => saveAiSettings().catch(handleError));
  $("localizationTranslateBtn").addEventListener("click", () => generateLocalizationTranslations().catch(handleError));
  $("localizationReloadBtn").addEventListener("click", () => loadConfig().catch(handleError));
  $("loadLocalizedBtn").addEventListener("click", () => loadLocalizedEditor().catch(handleError));
  $("saveLocalizedBtn").addEventListener("click", () => saveLocalizedAnnouncement().catch(handleError));
  $("deleteLocalizedBtn").addEventListener("click", () => deleteLocalizedAnnouncement().catch(handleError));
  $("newAnnouncementBtn").addEventListener("click", newAnnouncementDraft);
  $("loadAnnouncementBtn").addEventListener("click", () => loadAnnouncementForEdit().catch(handleError));
  $("saveAnnouncementBtn").addEventListener("click", () => saveAnnouncement().catch(handleError));
  $("editHistoryBtn").addEventListener("click", () => {
    const item = selectedHistory();
    if (!item || !confirmDiscard()) return;
    state.selectedAnnouncementId = item.id;
    renderAnnouncementForm(item);
    renderAnnouncementPreview();
    renderAnnouncementLoader();
    switchPanel("update");
  });
  $("setLatestHistoryBtn").addEventListener("click", () => setSelectedHistoryAsLatest().catch(handleError));
  $("deleteHistoryBtn").addEventListener("click", () => deleteSelectedHistory().catch(handleError));
  $("addNoticeBtn").addEventListener("click", addNotice);
  $("deleteNoticeBtn").addEventListener("click", deleteNotice);
  $("saveNoticesBtn").addEventListener("click", () => saveNotices().catch(handleError));
  $("addUpdateBtn").addEventListener("click", addUpdate);
  $("deleteUpdateBtn").addEventListener("click", deleteUpdate);
  $("saveUpdatesBtn").addEventListener("click", () => saveUpdates().catch(handleError));
  $("addDonorBtn").addEventListener("click", addDonor);
  $("deleteDonorBtn").addEventListener("click", deleteDonor);
  $("saveDonorsBtn").addEventListener("click", () => saveDonors().catch(handleError));
  $("uploadAssetBtn").addEventListener("click", () => uploadAsset().catch(handleError));
  $("validateBtn").addEventListener("click", () => runCommand("/api/validate").catch(handleError));
  $("buildBtn").addEventListener("click", () => runCommand("/api/build").catch(handleError));
  $("validateTopBtn").addEventListener("click", () => runCommand("/api/validate").catch(handleError));
  $("buildTopBtn").addEventListener("click", () => runCommand("/api/build").catch(handleError));

  $("historyList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-history-id]");
    if (!button) return;
    state.selectedHistoryId = button.dataset.historyId;
    renderHistoryList();
    renderHistoryPreview();
  });
  $("announcementLoader").addEventListener("change", () => {
    const annId = $("announcementLoader").value;
    const announcement = (state.data.history || []).find((item) => String(item.id) === String(annId));
    $("announcementLoadSummary").textContent = announcement
      ? `待加载：${announcement.version || announcement.title || announcement.id} / ${announcement.id}`
      : "当前目录没有可加载的公告。";
  });
  $("localizationAnnouncementId").addEventListener("change", () => {
    if (!confirmDiscard()) {
      $("localizationAnnouncementId").value = state.selectedLocalizationAnnouncementId;
      return;
    }
    state.selectedLocalizationAnnouncementId = $("localizationAnnouncementId").value;
    state.localizedEditor = null;
    renderLocalizedCoverage();
    renderLocalizedEditor();
    setDirty(false);
  });
  $("localizedLocale").addEventListener("change", () => {
    if (!confirmDiscard()) {
      $("localizedLocale").value = state.selectedLocalizationLocale;
      return;
    }
    state.selectedLocalizationLocale = $("localizedLocale").value;
    state.localizedEditor = null;
    renderLocalizedCoverage();
    renderLocalizedEditor();
    setDirty(false);
  });
  $("localizedCoverageList").addEventListener("click", (event) => {
    const card = event.target.closest("[data-localized-locale]");
    if (!card || card.disabled) return;
    if (!confirmDiscard()) return;
    state.selectedLocalizationLocale = card.dataset.localizedLocale;
    $("localizedLocale").value = state.selectedLocalizationLocale;
    loadLocalizedEditor().catch(handleError);
  });
  $("noticeList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-notice-index]");
    if (!button || !confirmDiscard()) return;
    state.selectedNotice = Number(button.dataset.noticeIndex);
    renderNoticeList();
    renderNoticeForm();
    renderNoticePreview();
    setDirty(false);
  });
  $("applyNoticeTestVersionBtn").addEventListener("click", () => {
    const version = $("noticeTestVersion").value.trim().replace(/^v/i, "");
    if (!version) {
      showMessage("请先填写临时测试版本。", "error");
      return;
    }
    $("noticeTestVersion").value = version;
    setVersionBoundarySelect("noticeMinVersion", version);
    setVersionBoundarySelect("noticeMaxVersion", version);
    setDirty(true);
    renderNoticePreview();
  });
  $("noticePublishClock").addEventListener("click", (event) => {
    if (!$("noticePublishDate").value) return;
    const modeButton = event.target.closest("[data-clock-mode]");
    if (modeButton) {
      $("noticePublishClock").dataset.mode = modeButton.dataset.clockMode;
      renderNoticeClock();
      return;
    }
    const valueButton = event.target.closest("[data-clock-value]");
    if (!valueButton) return;
    const mode = $("noticePublishClock").dataset.mode === "minute" ? "minute" : "hour";
    const value = Number(valueButton.dataset.clockValue);
    const parts = parseClockTime($("noticePublishTime").value);
    let hour = parts.hour;
    let minute = parts.minute;
    if (mode === "hour") {
      hour = value;
      minute ??= 0;
      $("noticePublishClock").dataset.mode = "minute";
    } else {
      minute = value;
      hour ??= 0;
    }
    $("noticePublishTime").value = formatClockTime(hour, minute);
    syncNoticePublishDateTime();
    renderNoticeClock();
    setDirty(true);
    renderNoticePreview();
  });
  $("noticeForm").addEventListener("change", (event) => {
    if (event.target.id === "noticePublishDate") {
      syncNoticePublishDateTime();
      renderNoticeClock();
    } else if (event.target.id === "noticeExpirePreset") {
      $("noticeExpireAt").value = $("noticeExpirePreset").value;
    }
    setDirty(true);
    renderNoticePreview();
  });
  $("updateList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-update-index]");
    if (!button || !confirmDiscard()) return;
    state.selectedUpdate = Number(button.dataset.updateIndex);
    renderUpdateList();
    renderUpdateForm();
    renderUpdatePreview();
    setDirty(false);
  });
  $("updateForm").addEventListener("change", (event) => {
    if (event.target.id === "updatePlatform") {
      $("updateUrl").value = legacyVersionInfoForPlatform($("updatePlatform").value)?.url || "";
    }
    if (event.target.id === "updateReleaseNoteId") {
      const note = (state.data.history || []).find((item) => String(item.id) === String($("updateReleaseNoteId").value));
      if (note?.version) {
        setSelectOptions("updateVersion", uniqueUpdateVersions(), note.version);
      }
    }
    if (event.target.id === "updateUrlPreset") {
      $("updateUrl").value = $("updateUrlPreset").value;
    } else if (event.target.id === "updatePublishPreset") {
      $("updatePublishAt").value = $("updatePublishPreset").value;
    } else if (event.target.id === "updateExpirePreset") {
      $("updateExpireAt").value = $("updateExpirePreset").value;
    } else if (["updatePlatform", "updateChannel", "updateVersion", "updateReleaseNoteId"].includes(event.target.id)) {
      syncUpdateDerivedFields();
    }
    setDirty(true);
    renderUpdatePreview();
  });
  $("donorList").addEventListener("click", (event) => {
    const button = event.target.closest("[data-donor-index]");
    if (!button || !confirmDiscard()) return;
    state.selectedDonor = Number(button.dataset.donorIndex);
    renderDonorList();
    renderDonorForm();
    renderDonorPreview();
    setDirty(false);
  });
  $("annNewDonors").addEventListener("change", (event) => {
    if (!event.target.closest("[data-multi-choice]")) return;
    updateMultiSelectSummary("annNewDonors");
    renderAnnouncementPreview();
    setDirty(true);
  });
  $("annItemsEditor").addEventListener("click", (event) => {
    const group = event.target.closest("[data-ann-item-index]");
    if (!group) return;
    const groupIndex = Number(group.dataset.annItemIndex);
    const addLineButton = event.target.closest("[data-add-ann-line]");
    if (addLineButton) {
      addAnnouncementItemLine(groupIndex, addLineButton.dataset.addAnnLine);
      return;
    }
    const deleteLineButton = event.target.closest("[data-delete-ann-line]");
    if (deleteLineButton) {
      deleteAnnouncementItemLine(groupIndex, deleteLineButton.dataset.deleteAnnLine, Number(deleteLineButton.dataset.lineIndex));
      return;
    }
    const deleteGroupButton = event.target.closest("[data-delete-ann-group]");
    if (deleteGroupButton) {
      deleteAnnouncementItemGroup(groupIndex);
    }
  });
  $("annItemsEditor").addEventListener("dragstart", handleAnnouncementItemDragStart);
  $("annItemsEditor").addEventListener("dragover", handleAnnouncementItemDragOver);
  $("annItemsEditor").addEventListener("drop", handleAnnouncementItemDrop);
  $("annItemsEditor").addEventListener("dragend", handleAnnouncementItemDragEnd);
  $("annItemsEditor").addEventListener("keydown", handleAnnouncementItemKeydown);
  $("annItemsEditor").addEventListener("input", () => {
    setDirty(true);
    renderAnnouncementPreview();
  });
  $("annItemsEditor").addEventListener("change", (event) => {
    if (!event.target.closest("[data-ann-item-category]")) return;
    setDirty(true);
    renderAnnouncementPreview();
  });
  $("localizedItemsEditor").addEventListener("input", () => {
    setDirty(true);
  });
  $("localizedItemsEditor").addEventListener("change", () => {
    setDirty(true);
  });

  document.querySelectorAll("input, select, textarea").forEach((input) => {
    const onEdit = () => {
      if (input.dataset.transient === "true") return;
      setDirty(true);
      if (input.closest("#announcementForm")) renderAnnouncementPreview();
      if (input.closest("#noticeForm")) renderNoticePreview();
      if (input.closest("#updateForm")) renderUpdatePreview();
      if (input.closest("#donorForm")) renderDonorPreview();
    };
    input.addEventListener("input", onEdit);
    if (input.tagName === "SELECT") {
      input.addEventListener("change", onEdit);
    }
  });
  window.addEventListener("beforeunload", (event) => {
    if (!state.dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });
}

function handleError(error) {
  console.error(error);
  const payload = error.payload;
  const detail = typeof payload === "object" ? JSON.stringify(payload, null, 2) : error.message;
  showMessage(detail, "error");
}

setupSelects();
attachEvents();
loadConfig().catch(handleError);
