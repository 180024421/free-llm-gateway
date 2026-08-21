# -*- coding: utf-8 -*-
"""Replace broken web/index.html script with a working one; patch HTML hooks."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = ROOT / "web" / "index.html"

CSS_EXTRA = """
.chip.warn{color:#fcd34d;border-color:rgba(245,158,11,.35)}
.btn-ok{background:rgba(34,197,94,.16);border-color:rgba(34,197,94,.35);color:#86efac}
.probe-list{display:grid;gap:8px}
.probe-item{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.02)}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:90;padding:20px}
.modal.show{display:flex}
.modal-card{width:min(460px,100%);background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 20px 50px rgba(0,0,0,.45)}
.modal-card h3{margin:0 0 6px}
"""

SCRIPT = r'''
const state = {
  overview: null,
  providers: [],
  routes: {},
  localKey: localStorage.getItem("dashuai_local_key") || "sk-local-change-me",
  dirtyProviders: false,
  openProvider: -1,
  lastProbes: [],
};

const PRESETS = {
  NVIDIA: {
    name: "NVIDIA",
    base_url: "https://integrate.api.nvidia.com/v1",
    models: ["meta/llama-3.1-8b-instruct", "nvidia/llama-3.1-nemotron-70b-instruct"],
    free_only: true,
    weight: 10,
    enabled: true,
  },
  ModelScope: {
    name: "ModelScope",
    base_url: "https://api-inference.modelscope.cn/v1",
    models: ["Qwen/Qwen2.5-72B-Instruct"],
    free_only: true,
    weight: 8,
    enabled: true,
  },
  "OpenAI-Compatible": {
    name: "OpenAI-Compatible",
    base_url: "https://api.openai.com/v1",
    models: ["gpt-4o-mini"],
    free_only: false,
    weight: 5,
    enabled: true,
  },
};

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

function toast(msg, err = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("err", !!err);
  el.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), 2600);
}

function authHeaders() {
  return { Authorization: `Bearer ${state.localKey}`, "Content-Type": "application/json" };
}

async function copyText(text) {
  const t = String(text || "").trim();
  if (!t) return;
  await navigator.clipboard.writeText(t);
  toast("已复制");
}

function go(page) {
  $$(".nav button[data-page]").forEach((b) => b.classList.toggle("active", b.dataset.page === page));
  $$(".page").forEach((p) => p.classList.toggle("active", p.id === `page-${page}`));
}

function esc(s) {
  return String(s ?? "").replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;");
}

function keyReady(k) {
  const s = String(k || "").trim();
  if (!s) return false;
  if (s.startsWith("REPLACE_")) return false;
  if (s.includes("YOUR_KEY") || s.includes("YOUR_API")) return false;
  if (s.includes("change-me") && !s.startsWith("sk-local")) return false;
  return true;
}

function normalizeProvider(p) {
  return {
    name: p.name || "unnamed",
    base_url: p.base_url || "",
    api_key: p.api_key || "",
    models: Array.isArray(p.models) ? p.models : [],
    free_only: !!p.free_only,
    weight: Number(p.weight ?? 1),
    enabled: p.enabled !== false,
  };
}

function findProviderIndex(list, name) {
  const n = String(name || "").toLowerCase();
  return list.findIndex((p) => {
    const pn = String(p.name || "").toLowerCase();
    return pn === n || pn.includes(n) || n.includes(pn);
  });
}

function upsertProvider(list, presetName, apiKey, baseUrl) {
  const key = String(apiKey || "").trim();
  const base = String(baseUrl || "").trim();
  if (!keyReady(key) && !base) return false;
  const preset = PRESETS[presetName];
  let i = findProviderIndex(list, presetName);
  if (i < 0) {
    list.push(
      normalizeProvider({
        ...preset,
        api_key: key || "",
        base_url: base || preset.base_url,
        enabled: keyReady(key),
      })
    );
    return true;
  }
  if (keyReady(key)) {
    list[i].api_key = key;
    list[i].enabled = true;
  }
  if (base) list[i].base_url = base;
  if (!list[i].models || !list[i].models.length) list[i].models = preset.models.slice();
  return true;
}

function wbSnippet(base, key) {
  return JSON.stringify(
    {
      id: "daily",
      name: "大帅网关 · daily",
      vendor: "Custom",
      url: base,
      apiKey: key,
      supportsToolCall: true,
      supportsImages: true,
      supportsReasoning: true,
      useCustomProtocol: false,
      onlyReasoning: false,
      maxInputTokens: 1048576,
      maxOutputTokens: 32768,
    },
    null,
    2
  );
}

function curlSnippet(base, key) {
  return `curl ${base}/chat/completions \\\n  -H "Authorization: Bearer ${key}" \\\n  -H "Content-Type: application/json" \\\n  -d "{\\"model\\":\\"daily\\",\\"messages\\":[{\\"role\\":\\"user\\",\\"content\\":\\"你好\\"}]}"`;
}

function cursorSnippet(base, key) {
  return JSON.stringify(
    {
      "dashuai-gateway": {
        name: "大帅网关",
        baseUrl: base,
        apiKey: key,
        models: Object.keys(state.routes || { daily: 1, fast: 1 }),
      },
    },
    null,
    2
  );
}

function renderChips(sel, routes) {
  const el = $(sel);
  const names = Object.keys(routes || {});
  if (!names.length) {
    el.innerHTML = `<span class="chip">暂无路由</span>`;
    return;
  }
  el.innerHTML = names
    .map((n) => `<button class="chip" type="button" data-copy-text="${esc(n)}">${esc(n)}</button>`)
    .join("");
  el.querySelectorAll("[data-copy-text]").forEach((b) => {
    b.onclick = () => copyText(b.dataset.copyText);
  });
}

function renderProbe(results) {
  const box = $("#probeBox");
  if (!box) return;
  if (!results || !results.length) {
    box.className = "empty";
    box.textContent = "还没有探测结果";
    return;
  }
  box.className = "probe-list";
  box.innerHTML = results
    .map((r) => {
      const cls = r.ok ? "ok" : "bad";
      const label = r.ok ? `成功 ${r.ms || 0}ms` : "失败";
      return `<div class="probe-item"><div><strong>${esc(r.name)}</strong><div class="desc" style="margin:4px 0 0">${esc(
        r.detail || ""
      )}</div></div><span class="chip ${cls}">${label}</span></div>`;
    })
    .join("");
}

function renderHome(j) {
  const ready = j.providers_ready || [];
  const routes = j.routes || {};
  const usage = j.usage || {};
  const online = !!j.ok;
  const base = j.openai_base || "http://127.0.0.1:8010/v1";

  $("#liveDot").classList.toggle("on", online);
  $("#liveText").textContent = online
    ? `在线 · ${ready.length} 个可用渠道 · :${j.config?.port || 8010}`
    : "离线";

  $("#statOnline").textContent = online ? "在线" : "离线";
  $("#statOnlineHint").textContent = base;
  $("#statReady").textContent = String(ready.length);
  $("#statReadyHint").textContent = ready.length ? ready.join(" / ") : "还没有可用 Key";
  $("#statRoutes").textContent = String(Object.keys(routes).length);
  $("#statCalls").textContent = String(usage.total ?? 0);
  $("#statCallsHint").textContent = `成功 ${usage.ok ?? 0}`;
  $("#navVer").textContent = `v${j.version || "—"}`;

  $("#homeBase").textContent = base;
  $("#connBase").textContent = base;
  $("#homeKey").textContent = state.localKey;
  $("#keyMasked").textContent = j.config?.local_api_key_masked || "—";
  renderChips("#homeRoutes", routes);
  renderChips("#connRoutes", routes);
  $("#wbSnippet").value = wbSnippet(base, state.localKey);

  const weakLocal =
    !state.localKey ||
    state.localKey === "sk-local-change-me" ||
    state.localKey.includes("change-me");

  const steps = [
    {
      done: ready.length > 0,
      title: "导入至少一个上游 Key",
      tip: "打开「一键配置」，填 Key 后点导入",
      action: "去配置",
      page: "setup",
    },
    {
      done: !weakLocal,
      title: "修改默认本地 Key",
      tip: "默认 Key 不安全，建议改成自己的",
      action: "去接入",
      page: "connect",
    },
    {
      done: Object.keys(routes).length > 0,
      title: "选用路由模型名",
      tip: "客户端 model 填 daily / fast",
      action: "看路由",
      page: "routes",
    },
    {
      done: (usage.total ?? 0) > 0,
      title: "发一次测试或同步 WorkBuddy",
      tip: "点「同步 WorkBuddy」后重启客户端",
      action: "去接入",
      page: "connect",
    },
  ];
  $("#homeSteps").innerHTML = steps
    .map(
      (s, i) => `
    <div class="step ${s.done ? "done" : ""}">
      <div class="n">${s.done ? "✓" : i + 1}</div>
      <div><div class="t">${s.title}</div><div class="s">${s.tip}</div></div>
      <button class="btn btn-secondary btn-sm" type="button" data-go="${s.page}">${s.action}</button>
    </div>`
    )
    .join("");
}

function renderMonitor(j) {
  const channels = j.channels || [];
  $("#channels").innerHTML = channels.length
    ? channels
        .map(
          (c) => `<tr>
      <td>${esc(c.provider)}</td><td>${esc(c.model)}</td><td>${c.score ?? "—"}</td>
      <td>${c.last_latency_ms != null ? c.last_latency_ms + " ms" : "—"}</td>
      <td>${c.circuit_open ? '<span class="chip bad">熔断</span>' : '<span class="chip ok">可用</span>'}</td>
    </tr>`
        )
        .join("")
    : `<tr><td colspan="5" style="color:var(--muted)">暂无调用记录</td></tr>`;

  const by = (j.usage || {}).by_provider || {};
  const names = Object.keys(by);
  if (!names.length) {
    $("#usageBox").className = "empty";
    $("#usageBox").textContent = "暂无用量";
  } else {
    $("#usageBox").className = "";
    $("#usageBox").innerHTML = names
      .map((n) => {
        const s = by[n];
        return `<div class="step done" style="margin-bottom:8px"><div class="n">●</div>
        <div><div class="t">${esc(n)}</div><div class="s">调用 ${s.calls ?? 0} · 成功 ${s.ok ?? 0}</div></div><span></span></div>`;
      })
      .join("");
  }
}

function renderProviders() {
  const list = state.providers;
  const ready = list.filter((p) => p.enabled && keyReady(p.api_key) && (p.models || []).length).length;
  $("#provSummary").textContent = `${list.length} 个渠道 · ${ready} 个可用`;
  $("#provDirty").classList.toggle("show", state.dirtyProviders);
  const box = $("#providers");
  if (!list.length) {
    box.innerHTML = `<div class="empty">还没有渠道</div>`;
    return;
  }
  box.innerHTML = list
    .map((p, i) => {
      const ok = p.enabled && keyReady(p.api_key) && (p.models || []).length > 0;
      return `<div class="provider ${state.openProvider === i ? "open" : ""}">
      <div class="provider-head" data-toggle="${i}">
        <div>
          <strong>${esc(p.name || "未命名")}</strong>
          <div class="provider-meta">
            <span class="chip ${ok ? "ok" : "bad"}">${ok ? "可用" : "待配置"}</span>
            <span class="chip">${p.enabled ? "已启用" : "已关闭"}</span>
          </div>
        </div>
        <div class="inline" onclick="event.stopPropagation()">
          <label class="switch"><input type="checkbox" data-f="enabled" data-i="${i}" ${
        p.enabled ? "checked" : ""
      }/>启用</label>
          <button class="btn btn-ghost btn-sm" type="button" data-probe="${i}">探测</button>
        </div>
      </div>
      <div class="provider-body">
        <div class="field"><label>名称</label><input data-f="name" data-i="${i}" value="${esc(p.name)}" /></div>
        <div class="field"><label>Base URL</label><input data-f="base_url" data-i="${i}" value="${esc(
        p.base_url
      )}" /></div>
        <div class="field"><label>API Key</label><input data-f="api_key" data-i="${i}" type="password" value="${esc(
        p.api_key
      )}" /></div>
        <div class="field"><label>模型（逗号分隔）</label><input data-f="models" data-i="${i}" value="${esc(
        (p.models || []).join(", ")
      )}" /></div>
        <div class="inline">
          <div class="field" style="flex:1;margin:0"><label>权重</label>
            <input data-f="weight" data-i="${i}" type="number" value="${p.weight ?? 1}" /></div>
          <button class="btn btn-danger btn-sm" type="button" data-del="${i}" style="margin-top:18px">删除</button>
        </div>
        <div class="chip" data-pr="${i}">未探测</div>
      </div>
    </div>`;
    })
    .join("");

  box.querySelectorAll("[data-toggle]").forEach((el) => {
    el.onclick = () => {
      const i = +el.dataset.toggle;
      state.openProvider = state.openProvider === i ? -1 : i;
      renderProviders();
    };
  });
  box.querySelectorAll("[data-f]").forEach((el) => {
    el.oninput = el.onchange = () => {
      const p = state.providers[+el.dataset.i];
      if (!p) return;
      const f = el.dataset.f;
      if (f === "enabled") p.enabled = el.checked;
      else if (f === "weight") p.weight = Number(el.value || 1);
      else if (f === "models") p.models = el.value.split(",").map((s) => s.trim()).filter(Boolean);
      else p[f] = el.value;
      state.dirtyProviders = true;
      $("#provDirty").classList.add("show");
    };
  });
  box.querySelectorAll("[data-probe]").forEach((b) => {
    b.onclick = (e) => {
      e.stopPropagation();
      probeOne(+b.dataset.probe);
    };
  });
  box.querySelectorAll("[data-del]").forEach((b) => {
    b.onclick = (e) => {
      e.stopPropagation();
      state.providers.splice(+b.dataset.del, 1);
      state.dirtyProviders = true;
      renderProviders();
    };
  });
}

function renderRoutes() {
  const box = $("#routesBox");
  const entries = Object.entries(state.routes || {});
  if (!entries.length) {
    box.innerHTML = `<div class="empty">暂无路由</div>`;
    return;
  }
  box.innerHTML = entries
    .map(
      ([id, m]) => `
    <div class="route" data-rid="${esc(id)}">
      <div class="name"><strong>${esc(id)}</strong>
        <button class="btn btn-ghost btn-sm" type="button" data-delr="${esc(id)}">删除</button>
      </div>
      <div class="field" style="margin-top:10px"><label>说明</label>
        <input data-rf="description" value="${esc((m || {}).description || "")}" /></div>
      <div class="field"><label>候选模型</label>
        <input data-rf="candidates" value="${esc(((m || {}).candidates || []).join(", "))}" /></div>
    </div>`
    )
    .join("");
  box.querySelectorAll("[data-delr]").forEach((b) => {
    b.onclick = () => {
      delete state.routes[b.dataset.delr];
      renderRoutes();
    };
  });
}

function collectRoutes() {
  const next = {};
  $$("#routesBox .route").forEach((card) => {
    next[card.dataset.rid] = {
      description: card.querySelector('[data-rf="description"]').value.trim(),
      candidates: card
        .querySelector('[data-rf="candidates"]')
        .value.split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    };
  });
  state.routes = next;
  return next;
}

async function saveProviders(show = true) {
  const r = await fetch("/api/providers", {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify(state.providers.map(normalizeProvider)),
  });
  if (!r.ok) throw new Error(await r.text());
  state.dirtyProviders = false;
  $("#provDirty").classList.remove("show");
  if (show) toast("渠道已保存");
  await refresh();
}

async function probeOne(i) {
  const p = state.providers[i];
  if (!p) return;
  const chip = document.querySelector(`[data-pr="${i}"]`);
  if (chip) chip.textContent = "探测中…";
  try {
    await saveProviders(false);
    const r = await fetch("/api/probe", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ name: p.name }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || "probe failed");
    const ok = !!j.ok;
    const ms = j.latency_ms || j.latency || 0;
    if (chip) chip.textContent = ok ? `成功 ${ms}ms` : "失败";
    toast(ok ? `${p.name} 探测成功` : `${p.name} 探测失败`, !ok);
    await refresh();
  } catch (e) {
    if (chip) chip.textContent = "失败";
    toast("探测失败：" + (e.message || "未知错误"), true);
  }
}

function parseSetupPaste() {
  const raw = (($("#setupPaste") && $("#setupPaste").value) || "").trim();
  if (!raw) {
    toast("粘贴区是空的", true);
    return;
  }
  const tokens = raw
    .split(/[\s,;|]+/)
    .map((s) => s.trim())
    .filter((s) => s.length >= 8);
  let nvidia = "",
    ms = "",
    oai = "";
  for (const t of tokens) {
    const low = t.toLowerCase();
    if (!nvidia && (low.startsWith("nvapi-") || low.startsWith("nvapi_") || low.includes("nvapi"))) nvidia = t;
    else if (!ms && (low.startsWith("ms-") || low.includes("modelscope"))) ms = t;
    else if (!oai && (low.startsWith("sk-") || low.startsWith("sk_"))) oai = t;
  }
  const rest = tokens.filter((t) => t !== nvidia && t !== ms && t !== oai);
  if (!nvidia && rest.length) nvidia = rest.shift();
  if (!ms && rest.length) ms = rest.shift();
  if (!oai && rest.length) oai = rest.shift();
  if (nvidia) $("#setupNvidia").value = nvidia;
  if (ms) $("#setupMs").value = ms;
  if (oai) $("#setupOai").value = oai;
  const n = [nvidia, ms, oai].filter(Boolean).length;
  if ($("#setupResult")) $("#setupResult").textContent = n ? "已识别 " + n + " 个 Key" : "未识别到 Key";
  toast(n ? "已识别 " + n + " 个 Key" : "未识别到 Key", !n);
}

async function importSetupKeys() {
  const nvidia = (($("#setupNvidia") && $("#setupNvidia").value) || "").trim();
  const ms = (($("#setupMs") && $("#setupMs").value) || "").trim();
  const oai = (($("#setupOai") && $("#setupOai").value) || "").trim();
  const oaiBase = (($("#setupOaiBase") && $("#setupOaiBase").value) || "").trim();
  if (!keyReady(nvidia) && !keyReady(ms) && !keyReady(oai) && !oaiBase) {
    toast("请至少填 1 个有效 Key", true);
    return false;
  }
  if ($("#setupResult")) $("#setupResult").textContent = "导入中…";
  if ($("#btnImportKeys")) $("#btnImportKeys").disabled = true;
  if ($("#btnImportCopy")) $("#btnImportCopy").disabled = true;
  if ($("#btnImportSync")) $("#btnImportSync").disabled = true;
  try {
    const pr = await fetch("/api/providers", { headers: authHeaders() });
    if (!pr.ok) throw new Error("auth " + pr.status);
    state.providers = ((await pr.json()) || []).map(normalizeProvider);
    const list = state.providers.slice();
    let n = 0;
    if (upsertProvider(list, "NVIDIA", nvidia)) n += 1;
    if (upsertProvider(list, "ModelScope", ms)) n += 1;
    if (upsertProvider(list, "OpenAI-Compatible", oai, oaiBase)) n += 1;
    state.providers = list;
    await saveProviders(false);
    if ($("#setupResult")) $("#setupResult").textContent = "已导入 " + n + " 项";
    toast("一键导入成功（" + n + " 项）");

    const results = [];
    for (const p of state.providers) {
      if (!(p.enabled && keyReady(p.api_key))) continue;
      try {
        const r = await fetch("/api/probe", {
          method: "POST",
          headers: authHeaders(),
          body: JSON.stringify({ name: p.name }),
        });
        const j = await r.json().catch(() => ({}));
        results.push({
          name: p.name,
          ok: !!j.ok,
          ms: j.latency_ms || j.latency || 0,
          detail: j.ok ? "连通正常" : j.detail || j.error || "探测失败",
        });
      } catch (e) {
        results.push({ name: p.name, ok: false, ms: 0, detail: String(e.message || e) });
      }
    }
    state.lastProbes = results;
    renderProbe(results);
    await refresh();
    return true;
  } catch (e) {
    console.error(e);
    if ($("#setupResult")) $("#setupResult").textContent = "导入失败";
    toast("导入失败：请确认本地 API Key 正确（一键接入页）", true);
    return false;
  } finally {
    if ($("#btnImportKeys")) $("#btnImportKeys").disabled = false;
    if ($("#btnImportCopy")) $("#btnImportCopy").disabled = false;
    if ($("#btnImportSync")) $("#btnImportSync").disabled = false;
  }
}

function clearSetupForm() {
  ["setupNvidia", "setupMs", "setupOai", "setupOaiBase", "setupPaste"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });
  if ($("#setupResult")) $("#setupResult").textContent = "已清空";
  renderProbe([]);
}

async function syncWorkBuddy() {
  try {
    const r = await fetch("/api/integrations/workbuddy", {
      method: "POST",
      headers: authHeaders(),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || "sync failed");
    toast("已同步 WorkBuddy：" + (j.path || ""));
    return true;
  } catch (e) {
    toast("同步失败：" + (e.message || "未知错误"), true);
    return false;
  }
}

async function refresh() {
  try {
    const r = await fetch("/api/overview");
    if (!r.ok) throw new Error("overview");
    const j = await r.json();
    state.overview = j;
    state.routes = j.routes || {};
    renderHome(j);
    renderMonitor(j);
    renderRoutes();
    if (j.port_warning) toast(j.port_warning, true);
  } catch (e) {
    $("#liveDot").classList.remove("on");
    $("#liveText").textContent = "无法连接网关";
  }
  try {
    const r = await fetch("/api/providers", { headers: authHeaders() });
    if (r.ok) {
      state.providers = ((await r.json()) || []).map(normalizeProvider);
      renderProviders();
    }
  } catch (_) {}
}

function maybeAskLocalKey() {
  if (localStorage.getItem("dashuai_key_prompted")) return;
  if (state.localKey !== "sk-local-change-me") return;
  if ($("#modalKey")) $("#modalKey").value = "sk-dashuai-" + Math.random().toString(36).slice(2, 10);
  if ($("#keyModal")) $("#keyModal").classList.add("show");
}

async function saveLocalKey(newKey) {
  const key = String(newKey || "").trim();
  if (!key) {
    toast("Key 不能为空", true);
    return false;
  }
  try {
    const curResp = await fetch("/api/config", { headers: authHeaders() });
    if (!curResp.ok) throw new Error("auth");
    const cur = await curResp.json();
    cur.local_api_key = key;
    const r = await fetch("/api/config", {
      method: "PUT",
      headers: authHeaders(),
      body: JSON.stringify(cur),
    });
    if (!r.ok) throw new Error("save");
    state.localKey = key;
    localStorage.setItem("dashuai_local_key", key);
    if ($("#localKey")) $("#localKey").value = key;
    if ($("#homeKey")) $("#homeKey").textContent = key;
    toast("本地 Key 已保存");
    await refresh();
    return true;
  } catch (_) {
    toast("保存失败：当前本地 Key 不正确", true);
    return false;
  }
}

// ---- wire events ----
$$(".nav button[data-page]").forEach((b) => {
  b.onclick = () => go(b.dataset.page);
});

document.body.addEventListener("click", (ev) => {
  const goBtn = ev.target.closest("[data-go]");
  if (goBtn && goBtn.dataset.go) go(goBtn.dataset.go);
  const copyBtn = ev.target.closest("[data-copy]");
  if (copyBtn) {
    const el = document.querySelector(copyBtn.dataset.copy);
    copyText(el ? el.textContent || el.value : "");
  }
});

if ($("#btnRefresh")) $("#btnRefresh").onclick = refresh;
if ($("#btnCopyAll"))
  $("#btnCopyAll").onclick = () => {
    const base = (state.overview && state.overview.openai_base) || $("#homeBase").textContent;
    copyText(`Base URL: ${base}\nAPI Key: ${state.localKey}\nModel: daily`);
  };

if ($("#localKey")) $("#localKey").value = state.localKey;
if ($("#btnToggleKey"))
  $("#btnToggleKey").onclick = () => {
    const el = $("#localKey");
    el.type = el.type === "password" ? "text" : "password";
    $("#btnToggleKey").textContent = el.type === "password" ? "显示" : "隐藏";
  };
if ($("#btnSaveKey")) $("#btnSaveKey").onclick = () => saveLocalKey($("#localKey").value);
if ($("#btnCopyWb")) $("#btnCopyWb").onclick = () => copyText($("#wbSnippet").value);
if ($("#btnCopyCurl"))
  $("#btnCopyCurl").onclick = () => {
    const base = (state.overview && state.overview.openai_base) || $("#connBase").textContent;
    copyText(curlSnippet(base, state.localKey));
  };
if ($("#btnCopyCursor"))
  $("#btnCopyCursor").onclick = () => {
    const base = (state.overview && state.overview.openai_base) || $("#connBase").textContent;
    copyText(cursorSnippet(base, state.localKey));
  };

async function onSyncWb() {
  await syncWorkBuddy();
}
if ($("#btnSyncWb")) $("#btnSyncWb").onclick = onSyncWb;
if ($("#btnSyncWb2")) $("#btnSyncWb2").onclick = onSyncWb;
if ($("#btnSyncWbTop")) $("#btnSyncWbTop").onclick = onSyncWb;

if ($("#btnImportKeys"))
  $("#btnImportKeys").onclick = async () => {
    if (await importSetupKeys()) go("connect");
  };
if ($("#btnImportCopy"))
  $("#btnImportCopy").onclick = async () => {
    if (!(await importSetupKeys())) return;
    const base = (state.overview && state.overview.openai_base) || $("#homeBase").textContent;
    await copyText("Base URL: " + base + "\nAPI Key: " + state.localKey + "\nModel: daily");
    go("connect");
  };
if ($("#btnImportSync"))
  $("#btnImportSync").onclick = async () => {
    if (await importSetupKeys()) {
      await syncWorkBuddy();
      go("connect");
    }
  };
if ($("#btnParsePaste")) $("#btnParsePaste").onclick = parseSetupPaste;
if ($("#btnClearSetup")) $("#btnClearSetup").onclick = clearSetupForm;

if ($("#btnAddProvider"))
  $("#btnAddProvider").onclick = () => {
    state.providers.push(
      normalizeProvider({
        ...PRESETS["OpenAI-Compatible"],
        name: `渠道-${state.providers.length + 1}`,
        api_key: "",
        enabled: true,
      })
    );
    state.openProvider = state.providers.length - 1;
    state.dirtyProviders = true;
    renderProviders();
  };
const saveProv = async () => {
  try {
    await saveProviders(true);
  } catch (_) {
    toast("保存失败：检查本地 API Key", true);
  }
};
if ($("#btnSaveProviders")) $("#btnSaveProviders").onclick = saveProv;
if ($("#btnSaveProviders2")) $("#btnSaveProviders2").onclick = saveProv;

if ($("#btnAddRoute"))
  $("#btnAddRoute").onclick = () => {
    collectRoutes();
    let i = 1,
      id = `route-${i}`;
    while (state.routes[id]) {
      i += 1;
      id = `route-${i}`;
    }
    state.routes[id] = { description: "新路由", candidates: [] };
    renderRoutes();
  };
if ($("#btnSaveRoutes"))
  $("#btnSaveRoutes").onclick = async () => {
    try {
      const body = collectRoutes();
      const r = await fetch("/api/routers", {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error(await r.text());
      toast("路由已保存");
      refresh();
    } catch (_) {
      toast("保存路由失败：检查本地 API Key", true);
    }
  };

if ($("#btnModalSave"))
  $("#btnModalSave").onclick = async () => {
    const ok = await saveLocalKey($("#modalKey").value);
    if (ok) {
      localStorage.setItem("dashuai_key_prompted", "1");
      $("#keyModal").classList.remove("show");
    }
  };
if ($("#btnModalSkip"))
  $("#btnModalSkip").onclick = () => {
    localStorage.setItem("dashuai_key_prompted", "1");
    $("#keyModal").classList.remove("show");
  };

refresh().then(() => {
  maybeAskLocalKey();
  const ready = (state.overview && state.overview.providers_ready) || [];
  if (!ready.length && !sessionStorage.getItem("dashuai_setup_seen")) {
    sessionStorage.setItem("dashuai_setup_seen", "1");
    go("setup");
    toast("先填 Key，再点「一键导入并启用」");
  }
});
setInterval(refresh, 15000);
'''


def main() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")

    if ".btn-ok{" not in html:
        html = html.replace(
            "@media (max-width:980px)",
            CSS_EXTRA + "\n@media (max-width:980px)",
            1,
        )

    # top actions: add sync button
    if 'id="btnSyncWbTop"' not in html:
        html = html.replace(
            '<button class="btn btn-ghost btn-sm" type="button" id="btnRefresh">刷新</button>',
            '<button class="btn btn-ghost btn-sm" type="button" id="btnRefresh">刷新</button>\n'
            '        <button class="btn btn-secondary btn-sm" type="button" id="btnSyncWbTop">同步 WorkBuddy</button>',
            1,
        )

    # nav foot
    html = html.replace("关掉窗口即退出", "可最小化到托盘")

    # setup actions: add import+sync + probe panel
    if 'id="btnImportSync"' not in html:
        html = html.replace(
            '<button class="btn btn-primary" type="button" id="btnImportKeys">一键导入并启用</button>',
            '<button class="btn btn-primary" type="button" id="btnImportKeys">一键导入并启用</button>\n'
            '            <button class="btn btn-ok" type="button" id="btnImportSync">导入并同步 WorkBuddy</button>',
            1,
        )

    if 'id="probeBox"' not in html:
        html = html.replace(
            """        <div class="panel">
          <h3>导入后做什么？</h3>
          <p class="desc">导入成功后，去「一键接入」复制 Base URL + 本地 Key 给客户端；模型名填 daily / fast。</p>
          <div class="inline">
            <button class="btn btn-secondary" type="button" data-go="connect">去一键接入</button>
            <button class="btn btn-ghost" type="button" data-go="providers">查看上游渠道</button>
          </div>
        </div>
      </div>""",
            """        <div class="panel">
          <h3>探测结果</h3>
          <p class="desc">导入后自动探测上游是否通；绿=成功，红=失败。</p>
          <div id="probeBox" class="empty">还没有探测结果</div>
        </div>
        <div class="panel">
          <h3>导入后做什么？</h3>
          <p class="desc">导入成功后：1) 同步 WorkBuddy 或复制接入信息；2) 客户端模型名填 daily / fast。</p>
          <div class="inline">
            <button class="btn btn-ok" type="button" id="btnSyncWb">同步 WorkBuddy</button>
            <button class="btn btn-secondary" type="button" data-go="connect">去一键接入</button>
            <button class="btn btn-ghost" type="button" data-go="providers">查看上游渠道</button>
          </div>
        </div>
      </div>""",
            1,
        )

    # connect page: sync + cursor export
    if 'id="btnSyncWb2"' not in html:
        html = html.replace(
            """            <div class="field"><label>路由模型</label><div class="chips" id="connRoutes"></div></div>
          </div>
          <div class="panel">
            <h3>配置片段</h3>
            <p class="desc">适合粘贴到自定义 OpenAI 兼容客户端。</p>
            <textarea id="wbSnippet" readonly></textarea>
            <div class="inline" style="margin-top:10px">
              <button class="btn btn-primary" type="button" id="btnCopyWb">复制片段</button>
              <button class="btn btn-secondary" type="button" id="btnCopyCurl">复制 curl 测试</button>
            </div>
          </div>""",
            """            <div class="field"><label>路由模型</label><div class="chips" id="connRoutes"></div></div>
            <div class="inline">
              <button class="btn btn-ok" type="button" id="btnSyncWb2">同步到 WorkBuddy</button>
              <button class="btn btn-secondary" type="button" id="btnCopyCursor">复制 Cursor 片段</button>
            </div>
          </div>
          <div class="panel">
            <h3>配置片段</h3>
            <p class="desc">适合粘贴到自定义 OpenAI 兼容客户端 / WorkBuddy。</p>
            <textarea id="wbSnippet" readonly></textarea>
            <div class="inline" style="margin-top:10px">
              <button class="btn btn-primary" type="button" id="btnCopyWb">复制片段</button>
              <button class="btn btn-secondary" type="button" id="btnCopyCurl">复制 curl 测试</button>
            </div>
          </div>""",
            1,
        )

    # modal
    if 'id="keyModal"' not in html:
        html = html.replace(
            '<div class="toast" id="toast"></div>',
            """<div class="modal" id="keyModal">
  <div class="modal-card">
    <h3>建议修改本地 API Key</h3>
    <p class="panel desc" style="margin:0 0 12px">当前还是默认 Key，任何人都能调用你的网关。改一个自己的更安全。</p>
    <div class="field"><label>新的本地 API Key</label><input id="modalKey" type="text" placeholder="例如 sk-dashuai-你的密码" /></div>
    <div class="inline">
      <button class="btn btn-primary" type="button" id="btnModalSave">保存并继续</button>
      <button class="btn btn-ghost" type="button" id="btnModalSkip">稍后</button>
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>""",
            1,
        )

    # replace script
    s0 = html.find("<script>")
    s1 = html.find("</script>", s0)
    if s0 < 0 or s1 < 0:
        raise SystemExit("script tag not found")
    html = html[: s0 + 8] + "\n" + SCRIPT.strip() + "\n" + html[s1:]

    HTML_PATH.write_text(html, encoding="utf-8")

    # verify compile
    script = HTML_PATH.read_text(encoding="utf-8")
    a = script.find("<script>") + 8
    b = script.find("</script>", a)
    compile(script[a:b], "index.html", "exec")
    print("OK wrote", HTML_PATH, "bytes", HTML_PATH.stat().st_size)


if __name__ == "__main__":
    main()
