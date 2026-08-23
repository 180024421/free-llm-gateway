
const state = {
  overview: null,
  providers: [],
  routes: {},
  localKey: localStorage.getItem("dashuai_local_key") || "sk-local-change-me",
  dirtyProviders: false,
  openProvider: 0,
  usageDays: 1,
};

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

function toast(msg, err=false){
  const el = $("#toast");
  if (!el) { try { alert(String(msg || "")); } catch(_){} return; }
  el.textContent = String(msg ?? "");
  el.classList.toggle("err", !!err);
  el.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), 3200);
}

function errText(x, fallback="操作失败"){
  if (x == null || x === "") return fallback;
  if (typeof x === "string") return x;
  if (typeof x === "object") {
    if (typeof x.detail === "string") return x.detail;
    if (x.detail && typeof x.detail.message === "string") return x.detail.message;
    if (typeof x.message === "string") return x.message;
    if (Array.isArray(x.detail)) {
      return x.detail.map(i => (i && (i.msg || i.message)) || JSON.stringify(i)).join("；") || fallback;
    }
    try { const s = JSON.stringify(x.detail || x); if (s && s !== "{}") return s.slice(0, 240); } catch(_){}
  }
  return fallback;
}

function authHeaders(){
  return { Authorization: `Bearer ${state.localKey}`, "Content-Type": "application/json" };
}

async function copyText(text){
  const t = String(text || "").trim();
  if (!t) return;
  await navigator.clipboard.writeText(t);
  toast("已复制");
}

const PRESETS = {
  NVIDIA: {
    name: "NVIDIA",
    base_url: "https://integrate.api.nvidia.com/v1",
    models: ["nvidia/nemotron-3-super-120b-a12b","nvidia/llama-3.3-nemotron-super-49b-v1","meta/llama-3.3-70b-instruct","meta/llama-3.1-8b-instruct","meta/llama-3.2-11b-vision-instruct","nvidia/nemotron-nano-12b-v2-vl"],
    free_only: true,
    weight: 10,
    enabled: true,
  },
  ModelScope: {
    name: "ModelScope",
    base_url: "https://api-inference.modelscope.cn/v1",
    models: ["Qwen/Qwen3.5-397B-A17B","Qwen/Qwen3-235B-A22B-Instruct-2507","deepseek-ai/DeepSeek-V4-Pro","deepseek-ai/DeepSeek-V4-Flash-0731","Qwen/Qwen3.5-122B-A10B","Qwen/Qwen3.5-27B","Qwen/Qwen3-Coder-30B-A3B-Instruct","Qwen/Qwen3-VL-235B-A22B-Instruct","Qwen/Qwen3-VL-8B-Instruct","Qwen/Qwen3-8B"],
    free_only: true,
    weight: 10,
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
    list.push(normalizeProvider({
      ...preset,
      api_key: key || "",
      base_url: base || preset.base_url,
      enabled: keyReady(key),
    }));
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

function parseSetupPaste() {
  const raw = ($("#setupPaste") && $("#setupPaste").value || "").trim();
  if (!raw) { toast("粘贴区是空的", true); return; }
  const tokens = raw.split(/[\s,;|]+/).map(s => s.trim()).filter(s => s.length >= 8);
  let nvidia = "", ms = "", oai = "";
  for (const t of tokens) {
    const low = t.toLowerCase();
    if (!nvidia && (low.startsWith("nvapi-") || low.startsWith("nvapi_") || low.includes("nvapi"))) nvidia = t;
    else if (!ms && (low.startsWith("ms-") || low.includes("modelscope"))) ms = t;
    else if (!oai && (low.startsWith("sk-") || low.startsWith("sk_"))) oai = t;
  }
  const rest = tokens.filter(t => t !== nvidia && t !== ms && t !== oai);
  if (!nvidia && rest.length) nvidia = rest.shift();
  if (!ms && rest.length) ms = rest.shift();
  if (!oai && rest.length) oai = rest.shift();
  if (nvidia) $("#setupNvidia").value = nvidia;
  if (ms) $("#setupMs").value = ms;
  if (oai) $("#setupOai").value = oai;
  const n = [nvidia, ms, oai].filter(Boolean).length;
  if ($("#setupResult")) $("#setupResult").textContent = n ? ("已识别 " + n + " 个 Key") : "未识别到 Key";
  toast(n ? ("已识别 " + n + " 个 Key") : "未识别到 Key", !n);
}

async function importSetupKeys() {
  const nvidia = ($("#setupNvidia") && $("#setupNvidia").value || "").trim();
  const ms = ($("#setupMs") && $("#setupMs").value || "").trim();
  const oai = ($("#setupOai") && $("#setupOai").value || "").trim();
  const oaiBase = ($("#setupOaiBase") && $("#setupOaiBase").value || "").trim();
  if (!keyReady(nvidia) && !keyReady(ms) && !keyReady(oai) && !oaiBase) {
    toast("请至少填 1 个 Key", true);
    return;
  }
  if ($("#setupResult")) $("#setupResult").textContent = "导入中…";
  if ($("#btnImportKeys")) $("#btnImportKeys").disabled = true;
  try {
    const pr = await fetch("/api/providers", { headers: authHeaders() });
    if (pr.ok) state.providers = ((await pr.json()) || []).map(normalizeProvider);
    const list = state.providers.slice();
    let n = 0;
    if (upsertProvider(list, "NVIDIA", nvidia)) n += 1;
    if (upsertProvider(list, "ModelScope", ms)) n += 1;
    if (upsertProvider(list, "OpenAI-Compatible", oai, oaiBase)) n += 1;
    state.providers = list;
    await saveProviders(false);
    if ($("#setupResult")) $("#setupResult").textContent = "已导入 " + n + " 项";
    toast("一键导入成功（" + n + " 项）");
    for (const p of state.providers) {
      if (p.enabled && keyReady(p.api_key)) {
        try {
          await fetch("/api/probe", {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({ name: p.name }),
          });
        } catch (_) {}
      }
    }
    await refresh();
    go("connect");
  } catch (e) {
    if ($("#setupResult")) $("#setupResult").textContent = "导入失败";
    toast("导入失败：请确认本地 API Key 正确", true);
  } finally {
    if ($("#btnImportKeys")) $("#btnImportKeys").disabled = false;
  }
}

function clearSetupForm() {
  ["setupNvidia", "setupMs", "setupOai", "setupOaiBase", "setupPaste"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });
  if ($("#setupResult")) $("#setupResult").textContent = "已清空";
}


function renderProbe(results){
  const box = document.getElementById("probeBox");
  if (!box) return;
  if (!results || !results.length){
    box.className = "empty";
    box.textContent = "还没有探测结果";
    return;
  }
  box.className = "probe-list";
  box.innerHTML = results.map(r => {
    const cls = r.ok ? "ok" : "bad";
    const label = r.ok ? (`成功 ${r.ms||0}ms`) : "失败";
    return `<div class="probe-item"><div><strong>${esc(r.name)}</strong><div style="margin-top:4px;color:var(--muted);font-size:12px">${esc(r.detail||"")}</div></div><span class="chip ${cls}">${label}</span></div>`;
  }).join("");
}

function currentLocalKeyFromUi(){
  const el = $("#localKey");
  const fromInput = el && el.value ? String(el.value).trim() : "";
  return fromInput || String(state.localKey || localStorage.getItem("dashuai_local_key") || "").trim();
}

function showWbWizard(wbPath){
  const modal = $("#wbWizardModal");
  const pathEl = $("#wbWizardPath");
  if (pathEl) pathEl.textContent = "路径：" + (wbPath || "~/.workbuddy/models.json");
  if (modal) modal.classList.add("show");
}
function hideWbWizard(){
  const modal = $("#wbWizardModal");
  if (modal) modal.classList.remove("show");
}
if ($("#btnWbWizardDone")) $("#btnWbWizardDone").onclick = () => hideWbWizard();
if ($("#btnWbWizardOpen")) $("#btnWbWizardOpen").onclick = () => {
  fetch("/api/integrations/workbuddy/diagnose").then(r => r.json()).then(j => {
    toast("请手动打开：" + (j.path || "~/.workbuddy/models.json"));
  }).catch(() => toast("路径：%USERPROFILE%\\.workbuddy\\models.json"));
};

async function saveAdvancedSettings(){
  try{
    const curResp = await fetch("/api/config", { headers: authHeaders() });
    if (!curResp.ok) return;
    const cur = await curResp.json();
    const sel = $("#novelPrefSelect");
    const teams = $("#agentTeamsToggle");
    const hedge = $("#fastHedgeToggle");
    const plimit = $("#providerLimitToggle");
    const uasync = $("#usageAsyncToggle");
    if (sel) cur.novel_preferred_provider = sel.value || "auto";
    const nstream = $("#novelStreamSelect");
    if (nstream) cur.novel_stream_mode = nstream.value || "safe";
    if (teams) cur.workbuddy_enable_agent_teams = !!teams.checked;
    if (hedge) cur.fast_hedged_requests = !!hedge.checked;
    if (plimit) cur.provider_concurrency_limit = !!plimit.checked;
    if (uasync) cur.usage_async_write = !!uasync.checked;
    const r = await fetch("/api/config", { method: "PUT", headers: authHeaders(), body: JSON.stringify(cur) });
    if (!r.ok) throw new Error("save");
    try { await fetch("/api/routers/rebuild-smart", { method: "POST", headers: authHeaders() }); } catch (_) {}
    toast("高级设置已保存");
  }catch(_){
    toast("保存高级设置失败", true);
  }
}
if ($("#novelPrefSelect")) $("#novelPrefSelect").onchange = () => saveAdvancedSettings();
if ($("#novelStreamSelect")) $("#novelStreamSelect").onchange = () => saveAdvancedSettings();
if ($("#agentTeamsToggle")) $("#agentTeamsToggle").onchange = () => saveAdvancedSettings();
if ($("#fastHedgeToggle")) $("#fastHedgeToggle").onchange = () => saveAdvancedSettings();
if ($("#providerLimitToggle")) $("#providerLimitToggle").onchange = () => saveAdvancedSettings();
if ($("#usageAsyncToggle")) $("#usageAsyncToggle").onchange = () => saveAdvancedSettings();

async function syncWorkBuddy(opts){
  const silent = !!(opts && opts.silent);
  try{
    const key = currentLocalKeyFromUi();
    if (key) {
      state.localKey = key;
      localStorage.setItem("dashuai_local_key", key);
      if ($("#localKey")) $("#localKey").value = key;
      if ($("#homeKey")) $("#homeKey").textContent = key;
    }
    const r = await fetch("/api/integrations/workbuddy", {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ local_api_key: key }),
    });
    const j = await r.json().catch(()=>({}));
    if (!r.ok) {
      const hint = (j.detail && j.detail.hint) ? (" " + j.detail.hint) : "";
      throw new Error(((j.detail && (j.detail.message || j.detail)) || j.detail || ("HTTP " + r.status)) + hint);
    }
    const ready = (j.providers_ready || []).length;
    const names = (j.models || []).map(m => m.id).join("、");
    const wbPath = (j.diagnose && j.diagnose.path) || (j.path || "~/.workbuddy/models.json");
    const keyLine = j.api_key_masked ? ("\n本地 Key 已写入 WorkBuddy：" + j.api_key_masked) : "";
    if (!silent) {
      if (!ready) {
        toast("已写入 WorkBuddy（" + (j.count || 0) + " 个用途），但还没有可用上游 Key。路径：" + wbPath + keyLine, true);
      } else {
        toast("已写入 " + (j.count || 0) + " 个用途到 WorkBuddy。" + keyLine + "\n路径：" + wbPath + "\n请完全退出并重启 WorkBuddy（任务栏右键退出，不是只关窗口）。\n模型：" + names);
        showWbWizard(wbPath);
      }
    }
    return { ok: true, ready, count: j.count || 0, path: wbPath, raw: j };
  }catch(e){
    if (!silent) toast("同步失败：" + (e.message||"未知错误"), true);
    return false;
  }
}

function cursorSnippet(base, key){
  return JSON.stringify({
    "dashuai-gateway": {
      name: "大帅网关",
      baseUrl: base,
      apiKey: key,
      models: Object.keys(state.routes || {"日常":1, "快速":1})
    }
  }, null, 2);
}

function go(page){
  const cur = document.querySelector(".page.active");
  const leavingProviders = cur && cur.id === "page-providers" && page !== "providers";
  if (leavingProviders && state.dirtyProviders) {
    toast("上游渠道有未保存修改，请先点「保存全部」", true);
    // 仍允许切换，但不触发会覆盖本地编辑的 refresh
  }
  $$(".nav button[data-page]").forEach(b => b.classList.toggle("active", b.dataset.page === page));
  $$(".page").forEach(p => p.classList.toggle("active", p.id === `page-${page}`));
  const content = $(".content");
  if (content) content.scrollTop = 0;
  if (page === "usage") {
    loadUsage();
    loadCallLog();
  }
  // dirty 时 refresh 也会跳过 providers，这里照常刷监控即可
  if (page === "monitor") refresh();
  if (page === "providers") renderProviders();
}

function esc(s){
  return String(s ?? "").replaceAll("&","&amp;").replaceAll('"',"&quot;").replaceAll("<","&lt;");
}

function keyReady(k){
  const s = String(k || "").trim();
  if (!s) return false;
  if (s.startsWith("REPLACE_") || s.includes("YOUR_KEY") || s.includes("change-me") || s === "sk-xxx") return false;
  return true;
}

/** 占位 Key 不当作已填写，避免密码框显示圆点误导 */
function displayApiKey(k){
  return keyReady(k) ? String(k) : "";
}

function normalizeProvider(p){
  const freeOnly = !!(p.free_only ?? p['free_only'] ?? p.freeOnly);
  const rawKey = p.api_key || "";
  return {
    name: p.name || "unnamed",
    base_url: p.base_url || "",
    api_key: displayApiKey(rawKey),
    models: Array.isArray(p.models) ? p.models : [],
    free_only: freeOnly,
    weight: Number(p.weight ?? 1),
    enabled: p.enabled !== false,
  };
}

function wbSnippet(base, key){
  return JSON.stringify({
    id: "日常",
    name: "日常 · 大帅网关",
    vendor: "Custom",
    url: base,
    apiKey: key,
    supportsToolCall: true,
    supportsImages: true,
    supportsReasoning: true,
    maxInputTokens: 1048576,
    maxOutputTokens: 32768
  }, null, 2);
}

function curlSnippet(base, key){
  return `curl ${base}/chat/completions \\\n  -H "Authorization: Bearer ${key}" \\\n  -H "Content-Type: application/json" \\\n  -d "{\\"model\\":\\"daily\\",\\"messages\\":[{\\"role\\":\\"user\\",\\"content\\":\\"你好\\"}]}"`;
}

function renderChips(sel, routes){
  const el = $(sel);
  const names = Object.keys(routes || {});
  if (!names.length){ el.innerHTML = `<span class="chip">暂无路由</span>`; return; }
  el.innerHTML = names.map(n => `<button class="chip" type="button" data-copy-text="${esc(n)}">${esc(n)}</button>`).join("");
  el.querySelectorAll("[data-copy-text]").forEach(b => b.onclick = () => copyText(b.dataset.copyText));
}

function renderHome(j){
  const ready = j.providers_ready || [];
  const routes = j.routes || {};
  const usage = j.usage || {};
  const ustat = usage.stats || usage.total_tokens || {};
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
  $("#statCalls").textContent = String(ustat.client_requests ?? ustat.requests ?? usage.total ?? 0);
  $("#statCallsHint").textContent = `上游 ${ustat.requests ?? usage.total ?? 0} 次 · 成功 ${ustat.ok ?? usage.ok ?? 0}`;
  $("#navVer").textContent = `v${j.version || "—"}`;

  const fails = j.recent_failures || [];
  const banner = $("#homeFailBanner");
  if (banner) {
    if (fails.length) {
      const f = fails[0];
      banner.classList.add("show");
      banner.innerHTML = `<b>最近失败</b> · ${esc(f.provider || "?")} / ${esc(f.model || "?")}：${esc(String(f.error || "").slice(0, 120))}<br><span style="font-size:12px;color:#fecaca">${esc(f.hint || "请到「上游渠道」或「运行监控」排查")}</span>`;
    } else {
      banner.classList.remove("show");
      banner.innerHTML = "";
    }
  }
  const failPanel = $("#homeFailPanel");
  const failList = $("#homeFailList");
  if (failPanel && failList) {
    if (fails.length) {
      failPanel.style.display = "";
      failList.innerHTML = fails.slice(0, 8).map(f =>
        `<div style="padding:8px 0;border-bottom:1px solid var(--line);font-size:13px">
          <div><span class="badge">${esc(f.provider||"?")}</span>${esc(f.model||"?")}</div>
          <div style="color:#fecaca;margin-top:4px">${esc(String(f.error||"").slice(0,160))}</div>
          <div style="color:var(--muted);font-size:12px;margin-top:4px">${esc(f.hint||"")}</div>
        </div>`
      ).join("");
    } else {
      failPanel.style.display = "none";
      failList.innerHTML = "";
    }
  }

  const lic = j.license || {};
  const pill = $("#accountPill");
  if (pill && lic.pending_usage_count > 0) {
    pill.title = (lic.pending_usage_last_error || "有用量待上报") + "（" + lic.pending_usage_count + " 条）";
  }

  $("#homeBase").textContent = base;
  $("#connBase").textContent = base;
  $("#homeKey").textContent = state.localKey;
  $("#keyMasked").textContent = j.config?.local_api_key_masked || "—";
  const np = $("#novelPrefSelect");
  if (np && j.config?.novel_preferred_provider) np.value = j.config.novel_preferred_provider;
  const ns = $("#novelStreamSelect");
  if (ns && j.config?.novel_stream_mode) ns.value = j.config.novel_stream_mode;
  const at = $("#agentTeamsToggle");
  if (at) at.checked = !!j.config?.workbuddy_enable_agent_teams;
  const fh = $("#fastHedgeToggle");
  if (fh) fh.checked = j.config?.fast_hedged_requests !== false;
  const pl = $("#providerLimitToggle");
  if (pl) pl.checked = j.config?.provider_concurrency_limit !== false;
  const ua = $("#usageAsyncToggle");
  if (ua) ua.checked = j.config?.usage_async_write !== false;
  renderChips("#homeRoutes", routes);
  renderChips("#connRoutes", routes);
  $("#wbSnippet").value = wbSnippet(base, state.localKey);

  const steps = [
    { done: ready.length > 0, title: "粘贴至少一个上游 API Key 并保存", tip: "上游渠道粘贴 Key（自动启用）→ 保存并同步 WorkBuddy", action: "去配置", page: "providers" },
    { done: !!j.config?.local_api_key_set, title: "确认本地网关 Key", tip: "客户端 API Key 必须与这里一致", action: "去接入", page: "connect" },
    { done: Object.keys(routes).length > 0, title: "选用路由模型名", tip: "WorkBuddy 选「日常 / 快速 / 识图 · 大帅网关」", action: "看路由", page: "routes" },
    { done: (usage.total ?? 0) > 0, title: "发一次测试请求", tip: "复制 curl，或用客户端随便问一句", action: "去接入", page: "connect" },
  ];
  $("#homeSteps").innerHTML = steps.map((s,i)=>`
    <div class="step ${s.done ? "done" : ""}">
      <div class="n">${s.done ? "✓" : (i+1)}</div>
      <div><div class="t">${s.title}</div><div class="s">${s.tip}</div></div>
      <button class="btn btn-secondary btn-sm" type="button" data-go="${s.page}">${s.action}</button>
    </div>`).join("");
  $$("#homeSteps [data-go]").forEach(b => b.onclick = () => go(b.dataset.go));
}

function fmtNum(n){
  n = Number(n || 0);
  if (n < 10000) return n.toLocaleString();
  if (n < 100000000) return (n / 10000).toFixed(1).replace(/\.0$/, "") + " 万";
  return (n / 100000000).toFixed(2).replace(/\.?0+$/, "") + " 亿";
}

function healthStatusChip(h){
  if (!h) return '<span class="chip">未探测</span>';
  if (h.status === "ok") return `<span class="chip ok">正常</span>`;
  if (h.status === "fail") return `<span class="chip bad">失败</span>`;
  return `<span class="chip warn">异常</span>`;
}

function renderMonitor(j){
  const channels = j.channels || [];
  const health = j.health || {};
  const tbody = $("#channels");
  const rows = [];

  // Prefer last probe map; fall back to runtime channel scores
  const keys = Object.keys(health);
  if (keys.length){
    keys.sort().forEach(k => {
      const [provider, model] = k.split("||");
      const h = health[k] || {};
      const ch = channels.find(c => c.provider === provider && c.model === model);
      rows.push(`<tr>
        <td>${esc(provider)}</td>
        <td>${esc(model)}</td>
        <td>${healthStatusChip(h)}${h.detail ? `<div style="margin-top:4px;color:var(--muted);font-size:11px">${esc(String(h.detail).slice(0,120))}</div>` : ""}</td>
        <td>${h.latency_ms != null ? h.latency_ms + " ms" : (ch && ch.last_latency_ms != null ? ch.last_latency_ms + " ms" : "—")}</td>
        <td>${ch ? (ch.circuit_open ? '<span class="chip bad">熔断</span>' : `<span class="chip ok">分 ${ch.score ?? "—"}</span>`) : "—"}</td>
      </tr>`);
    });
  } else if (channels.length){
    channels.forEach(c => {
      rows.push(`<tr>
        <td>${esc(c.provider)}</td>
        <td>${esc(c.model)}</td>
        <td><span class="chip">未探测</span></td>
        <td>${c.last_latency_ms != null ? c.last_latency_ms + " ms" : "—"}</td>
        <td>${c.circuit_open ? '<span class="chip bad">熔断</span>' : '<span class="chip ok">可用</span>'}</td>
      </tr>`);
    });
  }

  if (!rows.length){
    tbody.innerHTML = `<tr><td colspan="5" style="color:var(--muted)">尚无数据。配置渠道后点「立即检测」。</td></tr>`;
  } else {
    tbody.innerHTML = rows.join("");
  }

  const ps = j.poll_status || {};
  const el = $("#pollStatusText");
  if (el){
    if (ps.stage === "running") el.textContent = `检测中 ${ps.done||0}/${ps.total_models||0}`;
    else if (ps.last_poll_time) el.textContent = `上次检测 · ${ps.detail || "完成"}`;
    else el.textContent = "待命（可点立即检测）";
  }
}

async function loadUsage(){
  try{
    const r = await fetch(`/api/usage?days=${state.usageDays}`);
    if (!r.ok) throw new Error("usage " + r.status);
    renderUsage(await r.json());
  }catch(e){
    const body = $("#usageBody");
    if (body) body.innerHTML = `<tr><td colspan="5" style="color:var(--muted)">用量加载失败</td></tr>`;
  }
}

function renderUsage(data){
  const t = data.total || {};
  const cards = [
    { label: "输入 Token", value: t.pt },
    { label: "输出 Token", value: t.ct },
    { label: "合计 Token", value: t.tt },
    { label: "请求数", value: t.requests },
  ];
  $("#usageOverview").innerHTML = cards.map(c =>
    `<div class="stat-card"><div class="k">${c.label}</div><div class="v">${fmtNum(c.value)}</div></div>`
  ).join("");
  const rows = data.by_model || [];
  $("#usageBody").innerHTML = rows.length
    ? rows.map(r => `<tr>
        <td><span class="badge">${esc(r.provider || "?")}</span>${esc(r.model || "?")}</td>
        <td>${fmtNum(r.requests)}</td>
        <td>${fmtNum(r.pt)}</td>
        <td>${fmtNum(r.ct)}</td>
        <td>${fmtNum(r.tt)}</td>
      </tr>`).join("")
    : `<tr><td colspan="5" style="color:var(--muted)">暂无消耗记录</td></tr>`;
}

async function loadCallLog(){
  try{
    const r = await fetch("/api/call-log");
    if (!r.ok) throw new Error("call-log");
    const data = await r.json();
    const tbody = $("#callLogBody");
    if (!data || !data.length){
      tbody.innerHTML = `<tr><td colspan="4" style="color:var(--muted)">暂无调用记录</td></tr>`;
      return;
    }
    tbody.innerHTML = data.slice().reverse().map(d => {
      const ok = d.status === "ok";
      const err = d.error ? ` <span style="font-size:11px;color:#fecaca">(${esc(d.error)})</span>` : "";
      return `<tr>
        <td style="color:var(--muted);font-size:12px">${esc(d.time || "")}</td>
        <td>${ok ? '<span class="chip ok">成功</span>' : '<span class="chip bad">失败</span>'}${err}</td>
        <td><span class="badge">${esc(d.provider || "-")}</span>${esc(d.model || "-")}</td>
        <td style="font-variant-numeric:tabular-nums;color:var(--muted)">${d.tokens ? fmtNum(d.tokens) : "—"}</td>
      </tr>`;
    }).join("");
  }catch(_){}
}

async function checkAll(){
  const btn = $("#btnCheckAll");
  if (!btn) return;
  const old = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="spin">⟳</span> 检测中…`;
  try{
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 180000);
    const r = await fetch("/api/check/all", { method: "POST", headers: authHeaders(), signal: ctrl.signal });
    clearTimeout(timer);
    const results = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error((results.detail && (results.detail.message || results.detail)) || ("HTTP " + r.status));
    let ok = 0, fail = 0;
    Object.values(results).forEach(v => { if (v && v.status === "ok") ok++; else fail++; });
    toast(`检测完成：${ok} 正常 / ${fail} 异常`, fail > 0);
    await refresh();
  }catch(e){
    toast("检测失败：" + (e.name === "AbortError" ? "超时" : (e.message || "未知错误")), true);
  }finally{
    btn.disabled = false;
    btn.innerHTML = old;
  }
}

const PROVIDER_APPLY_HINTS = {
  "OpenAI-Compatible": {
    note: "通用 OpenAI 兼容槽位（官方 OpenAI 或任意中转）。不在「一键预设」列表里，需在此粘贴 Key 或到「一键配置」第 3 项导入。",
    signup: "https://platform.openai.com/api-keys",
    signupLabel: "OpenAI 官方申请 Key",
  },
  "Doubao": {
    note: "豆包走火山方舟。先在控制台创建「推理接入点」，模型列表里填接入点 ID（ep- 开头），不是网页版豆包账号。",
    signup: "https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement",
    signupLabel: "火山方舟创建接入点",
  },
  "Hunyuan": {
    note: "混元 API（元宝同底层）。用腾讯云控制台 sk- Key；hunyuan-lite 有免费额度，适合试写。",
    signup: "https://console.cloud.tencent.com/hunyuan/api-key",
    signupLabel: "混元 API Key",
  },
};

function providerApplyHint(name){
  const key = String(name || "");
  const hit = PROVIDER_APPLY_HINTS[key] || PROVIDER_APPLY_HINTS[key.replace(/\s+/g, "-")];
  if (!hit) return "";
  return `<p class="desc" style="margin:0 0 10px">${esc(hit.note)}${hit.signup ? ` <a class="hint-link" href="${esc(hit.signup)}" target="_blank" rel="noreferrer">${esc(hit.signupLabel || "打开申请页")}</a>` : ""}</p>`;
}

function renderProviders(){
  const box = $("#providers");
  const list = state.providers;
  const readyCount = list.filter(p => p.enabled && keyReady(p.api_key) && p.models.length).length;
  $("#provSummary").textContent = `${list.length} 个渠道 · ${readyCount} 个可用`;
  $("#provDirty").classList.toggle("show", state.dirtyProviders);

  if (!list.length){
    box.innerHTML = `<div class="empty">还没有渠道，点击右上角「新增渠道」</div>`;
    return;
  }

  box.innerHTML = list.map((p,i) => {
    const hasKey = keyReady(p.api_key);
    const ready = p.enabled && hasKey && (p.models || []).length > 0;
    const open = state.openProvider === i ? "open" : "";
    const statusChip = ready ? "可用" : (!hasKey ? "缺 API Key" : (!p.enabled ? "未启用" : "待配置"));
    return `<div class="provider ${open}" data-idx="${i}">
      <div class="provider-head" data-toggle="${i}">
        <div>
          <strong>${esc(p.name || "未命名")}</strong>
          <div class="provider-meta">
            <span class="chip ${ready ? "ok" : "bad"}">${statusChip}</span>
            <span class="chip">${p.enabled ? "已启用" : "已关闭"}</span>
            <span class="chip">权重 ${p.weight ?? 1}</span>
          </div>
        </div>
        <div class="inline" onclick="event.stopPropagation()">
          <label class="switch"><input type="checkbox" data-f="enabled" data-i="${i}" ${p.enabled ? "checked" : ""}/>启用</label>
          <button class="btn btn-ghost btn-sm" type="button" data-probe="${i}">探测</button>
        </div>
      </div>
      <div class="provider-body">
        ${providerApplyHint(p.name)}
        <div class="field"><label>名称</label><input data-f="name" data-i="${i}" value="${esc(p.name)}" /></div>
        <div class="field"><label>Base URL</label><input data-f="base_url" data-i="${i}" value="${esc(p.base_url)}" /></div>
        <div class="field"><label>API Key</label><input data-f="api_key" data-i="${i}" type="password" value="${esc(displayApiKey(p.api_key))}" placeholder="在此粘贴上游真实 Key（占位符不算）" autocomplete="off" /></div>
        <div class="field"><label>模型列表（逗号分隔）</label><input data-f="models" data-i="${i}" value="${esc((p.models || []).join(", "))}" /></div>
        <div class="inline">
          <div class="field" style="flex:1;margin:0"><label>权重</label><input data-f="weight" data-i="${i}" type="number" value="${p.weight ?? 1}" /></div>
          <label class="switch" style="margin-top:18px"><input type="checkbox" data-f="free_only" data-i="${i}" ${p.free_only ? "checked" : ""}/>仅免费</label>
          <button class="btn btn-danger btn-sm" type="button" data-del="${i}" style="margin-top:18px">删除</button>
        </div>
        <div class="chip" data-probe-result="${i}">未探测</div>
      </div>
    </div>`;
  }).join("");

  box.querySelectorAll("[data-toggle]").forEach(el => {
    el.onclick = () => {
      const i = Number(el.dataset.toggle);
      // 只切换展开，不整表重绘，避免输入框失焦后「无法再编辑」
      if (state.openProvider === i) {
        // 有未保存修改时禁止点标题折叠，否则表单被收起会像「坏了」
        if (state.dirtyProviders) {
          toast("请先保存或继续编辑当前渠道");
          return;
        }
        state.openProvider = -1;
      } else {
        state.openProvider = i;
      }
      box.querySelectorAll(".provider").forEach((card, idx) => {
        card.classList.toggle("open", idx === state.openProvider);
      });
    };
  });
  box.querySelectorAll("[data-f]").forEach(el => {
    el.onchange = el.oninput = () => {
      const i = Number(el.dataset.i);
      const f = el.dataset.f;
      const p = state.providers[i];
      if (!p) return;
      if (f === "enabled" || f === "free_only") p[f] = el.checked;
      else if (f === "weight") p.weight = Number(el.value || 1);
      else if (f === "models") p.models = el.value.split(",").map(s => s.trim()).filter(Boolean);
      else p[f] = el.value;
      state.dirtyProviders = true;
      // auto-enable-marker: 粘贴有效 Key 后自动勾选启用
      if (f === "api_key" && keyReady(el.value)) {
        p.api_key = el.value;
        p.enabled = true;
        const sw = el.closest(".provider") && el.closest(".provider").querySelector('input[data-f="enabled"]');
        if (sw) sw.checked = true;
      }
      $("#provDirty").classList.add("show");
      // 启用开关在标题栏：就地更新标签，不重绘
      if (f === "enabled") {
        const card = el.closest(".provider");
        const chips = card && card.querySelectorAll(".provider-meta .chip");
        if (chips && chips[1]) chips[1].textContent = el.checked ? "已启用" : "已关闭";
      }
    };
  });
  box.querySelectorAll("[data-probe]").forEach(btn => {
    btn.onclick = (e) => { e.stopPropagation(); probeOne(Number(btn.dataset.probe)); };
  });
  box.querySelectorAll("[data-del]").forEach(btn => {
    btn.onclick = (e) => {
      e.stopPropagation();
      state.providers.splice(Number(btn.dataset.del), 1);
      state.dirtyProviders = true;
      state.openProvider = Math.min(state.openProvider, state.providers.length - 1);
      renderProviders();
    };
  });
}

function renderRoutes(){
  const box = $("#routesBox");
  const entries = Object.entries(state.routes || {});
  if (!entries.length){ box.innerHTML = `<div class="empty">暂无路由</div>`; return; }
  box.innerHTML = entries.map(([id, meta]) => {
    const m = meta || {};
    const candidates = Array.isArray(m.candidates) ? m.candidates.join(", ") : "";
    return `<div class="route" data-rid="${esc(id)}">
      <div class="name"><strong>${esc(id)}</strong><button class="btn btn-ghost btn-sm" type="button" data-del-route="${esc(id)}">删除</button></div>
      <div class="field" style="margin-top:10px"><label>说明</label><input data-rf="description" value="${esc(m.description || "")}" /></div>
      <div class="field"><label>候选模型（逗号分隔，按优先级）</label><input data-rf="candidates" value="${esc(candidates)}" /></div>
    </div>`;
  }).join("");
  box.querySelectorAll("[data-del-route]").forEach(btn => {
    btn.onclick = () => { delete state.routes[btn.dataset.delRoute]; renderRoutes(); };
  });
}

function collectRoutesFromDom(){
  const next = {};
  $$("#routesBox .route").forEach(card => {
    const id = card.dataset.rid;
    next[id] = {
      description: card.querySelector('[data-rf="description"]').value.trim(),
      candidates: card.querySelector('[data-rf="candidates"]').value.split(",").map(s => s.trim()).filter(Boolean),
    };
  });
  state.routes = next;
  return next;
}

async function saveProviders(showToast=true){
  // 分发场景：有有效 Key 即启用；占位 Key 清空，避免误判已配置
  for (const p of (state.providers || [])) {
    if (!keyReady(p.api_key)) p.api_key = "";
    else p.enabled = true;
  }
  const r = await fetch("/api/providers", {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify(state.providers),
  });
  if (!r.ok) throw new Error(await r.text());
  state.dirtyProviders = false;
  $("#provDirty").classList.remove("show");
  const readyN = (state.providers || []).filter(p => p.enabled && keyReady(p.api_key) && (p.models||[]).length).length;
  if (showToast) {
    if (readyN) toast(`渠道已保存（${readyN} 个可用）`);
    else toast("渠道已保存，但还没有有效 API Key——请粘贴真实 Key（密码框里的圆点若是占位符不算）", true);
  }
  renderProviders();
  await refresh();
}

async function probeOne(idx){
  const p = state.providers[idx];
  if (!p) return;
  const chip = document.querySelector(`[data-probe-result="${idx}"]`);
  if (chip) chip.textContent = "探测中…";
  try{
    await saveProviders(false);
    const r = await fetch("/api/probe", {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ name: p.name }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || "probe failed");
    if (chip) chip.textContent = j.ok ? `成功 ${j.latency_ms || j.latency || 0}ms` : "失败";
    toast(j.ok ? `${p.name} 探测成功` : `${p.name} 探测失败`, !j.ok);
    refresh();
  }catch(e){
    if (chip) chip.textContent = "失败";
    toast("探测失败：请检查 Key / 网络 / 本地 Key", true);
  }
}

async function refresh(){
  try{
    const r = await fetch("/api/overview");
    if (!r.ok) throw new Error("overview");
    const j = await r.json();
    state.overview = j;
    state.routes = j.routes || {};
    if (j.license && typeof window.paintLicense === "function") window.paintLicense(j.license);
    renderHome(j);
    renderMonitor(j);
    renderRoutes();
  }catch(e){
    $("#liveDot").classList.remove("on");
    $("#liveText").textContent = "无法连接网关";
    toast("网关未响应", true);
  }
  // 有未保存修改时绝不覆盖本地编辑（否则 15 秒轮询会冲掉新增渠道）
  if (state.dirtyProviders) return;
  try{
    const r = await fetch("/api/providers", { headers: authHeaders() });
    if (r.ok){
      state.providers = (await r.json() || []).map(normalizeProvider);
      renderProviders();
    }
  }catch(_){}
}

$$(".nav button[data-page]").forEach(b => b.onclick = () => go(b.dataset.page));
document.body.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-copy]");
  if (btn){
    const el = document.querySelector(btn.dataset.copy);
    copyText(el?.textContent || el?.value || "");
  }
});

$("#btnCopyAll").onclick = async () => {
  const base = state.overview?.openai_base || $("#homeBase").textContent;
  await copyText(`Base URL: ${base}\nAPI Key: ${state.localKey}\nModel: 日常`);
};
$("#btnCopyWb").onclick = () => copyText($("#wbSnippet").value);
$("#btnCopyCurl").onclick = () => {
  const base = state.overview?.openai_base || $("#connBase").textContent;
  copyText(curlSnippet(base, state.localKey));
};
$("#btnRefresh").onclick = refresh;
$("#btnCheckAll").onclick = checkAll;
$$("#usageTabs [data-days]").forEach(btn => {
  btn.onclick = () => {
    state.usageDays = Number(btn.dataset.days) || 1;
    $$("#usageTabs [data-days]").forEach(b => b.classList.toggle("active", b === btn));
    loadUsage();
    loadCallLog();
  };
});
setInterval(() => {
  if ($("#page-usage")?.classList.contains("active")) loadCallLog();
}, 5000);
if ($("#btnRefreshUsage")) $("#btnRefreshUsage").onclick = () => { loadUsage(); loadCallLog(); toast("已刷新消耗"); };

$("#localKey").value = state.localKey;
$("#btnToggleKey").onclick = () => {
  const el = $("#localKey");
  el.type = el.type === "password" ? "text" : "password";
  $("#btnToggleKey").textContent = el.type === "password" ? "显示" : "隐藏";
};
$("#btnSaveKey").onclick = async () => {
  const newKey = $("#localKey").value.trim();
  if (!newKey) return toast("Key 不能为空", true);
  try{
    const curResp = await fetch("/api/config", { headers: authHeaders() });
    if (!curResp.ok) throw new Error("auth");
    const cur = await curResp.json();
    cur.local_api_key = newKey;
    const r = await fetch("/api/config", { method: "PUT", headers: authHeaders(), body: JSON.stringify(cur) });
    if (!r.ok) throw new Error(await r.text());
    state.localKey = newKey;
    localStorage.setItem("dashuai_local_key", newKey);
    $("#homeKey").textContent = newKey;
    const syncRes = await syncWorkBuddy({ silent: true });
    const masked = (syncRes && syncRes.raw && syncRes.raw.api_key_masked) || newKey;
    toast("本地 Key 已保存并同步到 WorkBuddy（" + masked + "）。请完全退出并重启 WorkBuddy。");
    refresh();
  }catch(e){
    toast("保存失败：当前本地 Key 不正确", true);
  }
};

$("#btnAddProvider").onclick = () => {
  state.providers.push(normalizeProvider({
    name: `渠道-${state.providers.length + 1}`,
    base_url: "https://api.example.com/v1",
    api_key: "",
    models: ["demo-model"],
    free_only: true,
    weight: 1,
    enabled: true,
  }));
  state.openProvider = state.providers.length - 1;
  state.dirtyProviders = true;
  renderProviders();
  // 自动聚焦名称，方便继续填写；填完后务必点「保存」
  const nameInput = document.querySelector(`#providers .provider.open input[data-f="name"]`);
  if (nameInput) {
    nameInput.focus();
    nameInput.select();
  }
  toast("已新增渠道，编辑后请点「保存全部」");
};
const saveProv = async () => {
  try { await saveProviders(true); }
  catch { toast("保存失败：检查本地 API Key", true); }
};
$("#btnSaveProviders").onclick = saveProv;
$("#btnSaveProviders2").onclick = saveProv;

$("#btnAddRoute").onclick = () => {
  collectRoutesFromDom();
  let i = 1, id = `route-${i}`;
  while (state.routes[id]) { i += 1; id = `route-${i}`; }
  state.routes[id] = { description: "新路由", candidates: [] };
  renderRoutes();
};
$("#btnSaveRoutes").onclick = async () => {
  try{
    const body = collectRoutesFromDom();
    const r = await fetch("/api/routers", { method: "PUT", headers: authHeaders(), body: JSON.stringify(body) });
    if (!r.ok) throw new Error(await r.text());
    toast("路由已保存");
    refresh();
  }catch{
    toast("保存路由失败：检查本地 API Key", true);
  }
};
if ($("#btnRebuildSmartRoutes")) $("#btnRebuildSmartRoutes").onclick = async () => {
  try {
    await rebuildSmartRoutes(true);
    await refresh();
  } catch (e) {
    toast("按日志优选失败：" + (e.message || "未知错误"), true);
  }
};


if ($("#btnImportKeys")) $("#btnImportKeys").onclick = importSetupKeys;

if ($("#btnImportSync")) $("#btnImportSync").onclick = async () => {
  await importSetupKeys();
  await syncWorkBuddy();
};
if ($("#btnSyncWb")) $("#btnSyncWb").onclick = () => syncWorkBuddy();
if ($("#btnSyncWb2")) $("#btnSyncWb2").onclick = () => syncWorkBuddy();
if ($("#btnSyncWbTop")) $("#btnSyncWbTop").onclick = () => syncWorkBuddy();
if ($("#btnCopyCursor")) $("#btnCopyCursor").onclick = () => {
  const base = (state.overview && state.overview.openai_base) || ($("#connBase") && $("#connBase").textContent) || "";
  copyText(cursorSnippet(base, state.localKey));
};
if ($("#btnModalSave")) $("#btnModalSave").onclick = async () => {
  const key = (($("#modalKey") && $("#modalKey").value) || "").trim();
  if (!key) { toast("请填写新 Key", true); return; }
  if ($("#localKey")) $("#localKey").value = key;
  localStorage.setItem("dashuai_key_prompted", "1");
  if ($("#keyModal")) $("#keyModal").classList.remove("show");
  if ($("#btnSaveKey")) await $("#btnSaveKey").onclick();
};
if ($("#btnModalSkip")) $("#btnModalSkip").onclick = () => {
  localStorage.setItem("dashuai_key_prompted", "1");
  if ($("#keyModal")) $("#keyModal").classList.remove("show");
};
(function maybeAskKey(){
  if (localStorage.getItem("dashuai_key_prompted")) return;
  if (state.localKey !== "sk-local-change-me") return;
  if ($("#modalKey")) $("#modalKey").value = "sk-dashuai-" + Math.random().toString(36).slice(2,10);
  if ($("#keyModal")) $("#keyModal").classList.add("show");
})();


if ($("#btnImportCopy")) $("#btnImportCopy").onclick = async () => {
  await importSetupKeys();
  const base = (state.overview && (state.overview.openai_base || state.overview.openai_base)) || ($("#homeBase") && $("#homeBase").textContent) || "";
  await copyText("Base URL: " + base + "\nAPI Key: " + state.localKey + "\nModel: 日常");
};

if ($("#btnParsePaste")) $("#btnParsePaste").onclick = parseSetupPaste;
if ($("#btnClearSetup")) $("#btnClearSetup").onclick = clearSetupForm;
document.body.addEventListener("click", (ev) => {
  const goBtn = ev.target.closest("[data-go]");
  if (goBtn && goBtn.dataset.go) go(goBtn.dataset.go);
});
(function firstRunSetup(){
  setTimeout(async () => {
    try {
      const r = await fetch("/api/overview");
      if (!r.ok) return;
      const j = await r.json();
      const ready = j.providers_ready || [];
      if (!ready.length && !sessionStorage.getItem("dashuai_setup_seen")) {
        sessionStorage.setItem("dashuai_setup_seen", "1");
        go("providers");
        toast("粘贴上游 API Key → 点「保存并同步 WorkBuddy」→ 重启 WorkBuddy");
      }
    } catch (_) {}
  }, 500);
})();

refresh();
setInterval(refresh, 15000);



/* === CHANNEL_PRESET_PICKER === */
const CHANNEL_PRESETS = [
  // 顺序与 data/providers.example.json 对齐（2026-08-22 实测校准）
  {id:"ModelScope", name:"ModelScope", region:"cn", note:"魔搭：国内直连，含识图 VL", signup:"https://modelscope.cn/my/myaccesstoken", base_url:"https://api-inference.modelscope.cn/v1", models:["Qwen/Qwen3.5-397B-A17B", "Qwen/Qwen3-235B-A22B-Instruct-2507", "deepseek-ai/DeepSeek-V4-Pro", "deepseek-ai/DeepSeek-V4-Flash-0731", "Qwen/Qwen3.5-122B-A10B", "Qwen/Qwen3.5-27B", "Qwen/Qwen3-Coder-30B-A3B-Instruct", "Qwen/Qwen3-VL-235B-A22B-Instruct", "Qwen/Qwen3-VL-8B-Instruct", "Qwen/Qwen3-8B"], free_only:true, weight:10, defaultOn:true},
  {id:"SiliconFlow", name:"SiliconFlow", region:"cn", note:"硅基：需账户余额；已换成当前小杯/常用 ID", signup:"https://cloud.siliconflow.cn/account/ak", base_url:"https://api.siliconflow.cn/v1", models:["Qwen/Qwen3.5-9B", "Qwen/Qwen3.5-4B", "Qwen/Qwen3-8B", "THUDM/GLM-4-9B-0414", "Qwen/Qwen2.5-7B-Instruct", "deepseek-ai/DeepSeek-V3"], free_only:true, weight:9, defaultOn:true},
  {id:"Zhipu", name:"Zhipu", region:"cn", note:"智谱：整段 API Key（id.secret）；已加 glm-5.x", signup:"https://open.bigmodel.cn/usercenter/apikeys", base_url:"https://open.bigmodel.cn/api/paas/v4", models:["glm-5.2", "glm-5.1", "glm-5", "glm-4.7", "glm-4.6", "glm-4.5", "glm-4.7-flash", "glm-4.5-flash"], free_only:true, weight:8, defaultOn:true},
  {id:"SenseNova", name:"SenseNova", region:"cn", note:"商汤 Token Plan：必须用 token.sensenova.cn（旧 api.sensenova.cn 会 403）", signup:"https://console.sensenova.cn/", base_url:"https://token.sensenova.cn/v1", models:["sensenova-6.8-flash-lite", "sensenova-6.7-flash-lite", "deepseek-v4-flash", "glm-5.2"], free_only:true, weight:9, defaultOn:true},
  {id:"Doubao", name:"豆包(火山方舟)", region:"cn", note:"火山方舟 OpenAI 兼容；控制台「推理接入点」创建后，模型名填接入点 ID（ep- 开头）或下方示例 ID；新用户有免费 Token", signup:"https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement", base_url:"https://ark.cn-beijing.volces.com/api/v3", models:["doubao-seed-1-6-251015", "doubao-lite-32k-240828", "doubao-seed-1-8-251228"], free_only:true, weight:10, defaultOn:true},
  {id:"Hunyuan", name:"混元(元宝API)", region:"cn", note:"腾讯云混元，与元宝同底层；控制台申请 sk- 开头 Key；hunyuan-lite 有免费额度", signup:"https://console.cloud.tencent.com/hunyuan/api-key", base_url:"https://api.hunyuan.cloud.tencent.com/v1", models:["hunyuan-turbos-latest", "hunyuan-lite", "hunyuan-turbo"], free_only:true, weight:9, defaultOn:true},
  {id:"NVIDIA", name:"NVIDIA", region:"vpn", note:"NVIDIA NIM：含视觉；建议 VPN", signup:"https://build.nvidia.com/", base_url:"https://integrate.api.nvidia.com/v1", models:["nvidia/nemotron-3-super-120b-a12b", "nvidia/llama-3.3-nemotron-super-49b-v1", "meta/llama-3.3-70b-instruct", "meta/llama-3.1-8b-instruct", "meta/llama-3.2-11b-vision-instruct", "nvidia/nemotron-nano-12b-v2-vl"], free_only:true, weight:10, defaultOn:true},
  {id:"Groq", name:"Groq", region:"vpn", note:"Groq：需 VPN；旧 llama/qwen ID 已下架", signup:"https://console.groq.com/keys", base_url:"https://api.groq.com/openai/v1", models:["openai/gpt-oss-120b", "openai/gpt-oss-20b", "groq/compound", "allam-2-7b"], free_only:true, weight:9, defaultOn:false},
  {id:"Gemini", name:"Gemini", region:"vpn", note:"Gemini：flash-latest / 3.x；pro-latest 易触配额", signup:"https://aistudio.google.com/apikey", base_url:"https://generativelanguage.googleapis.com/v1beta/openai/", models:["gemini-flash-latest", "gemini-3-flash-preview", "gemini-3.1-flash-lite-preview", "gemini-2.5-flash"], free_only:true, weight:9, defaultOn:false},
  {id:"Cerebras", name:"Cerebras", region:"vpn", note:"Cerebras：需 VPN；旧 llama/qwen ID 已下架；部分模型要付费", signup:"https://cloud.cerebras.ai/", base_url:"https://api.cerebras.ai/v1", models:["gemma-4-31b", "gpt-oss-120b"], free_only:true, weight:8, defaultOn:false},
  {id:"OpenRouter", name:"OpenRouter", region:"vpn", note:"OpenRouter：用当前 :free；旧 glm-5.1:free / lfm-1.2b 已失效", signup:"https://openrouter.ai/keys", base_url:"https://openrouter.ai/api/v1", models:["openrouter/free", "z-ai/glm-5.2:free", "google/gemma-4-31b-it:free", "nvidia/nemotron-3-nano-30b-a3b:free", "nvidia/nemotron-3-super-120b-a12b:free", "liquid/lfm-2.5-2.6b:free"], free_only:true, weight:7, defaultOn:false},
  {id:"Mistral", name:"Mistral", region:"vpn", note:"Mistral：需 VPN；保留当前可用 small/ministral", signup:"https://console.mistral.ai/api-keys/", base_url:"https://api.mistral.ai/v1", models:["mistral-small-latest", "mistral-small-2603", "magistral-small-latest", "ministral-8b-latest", "open-mistral-nemo"], free_only:true, weight:6, defaultOn:false},
];

async function rebuildSmartRoutes(showToast=true){
  const r = await fetch("/api/routers/rebuild-smart", { method: "POST", headers: authHeaders() });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || j.message || "rebuild failed");
  state.routes = j.routes || {};
  if (typeof renderRoutes === "function") renderRoutes();
  if (showToast) {
    const n = (j.summary || []).length;
    toast("已按日志重建 " + n + " 类路由（每类最多10个：成功率+准确度+速度）");
  }
  return j;
}

function rebuildWorkBuddyRoutesFromProviders(list){
  // 保留作离线兜底；正常走 /api/routers/rebuild-smart
  // 按渠道权重收集模型，重建 WorkBuddy 需要的中文路由名
  const ranked = (list || []).slice().sort((a,b) => (b.weight||0) - (a.weight||0));
  const all = [];
  const seen = new Set();
  for (const p of ranked){
    for (const m of (p.models || [])){
      if (!m || seen.has(m)) continue;
      seen.add(m);
      all.push(String(m));
    }
  }
  const pick = (pred, fallback) => {
    const hit = all.filter(pred);
    const src = hit.length ? hit : fallback;
    return src.filter((m,i,a) => a.indexOf(m)===i).slice(0, 16);
  };
  const isVL = m => /vl|vision|flash-latest|gemini-3-flash|gemma|识图/i.test(m);
  const isNovel = m => /122b|235b|v4-pro|deepseek-v4-pro|glm-5\.|pro/i.test(m) && !/397b|550b|241b|80b-a3b-thinking/i.test(m);
  const isFast = m => /flash|8b|7b|mini|instant|lite|nemo|small|2\.5-7b|qwen3-8b|flash-latest/i.test(m);
  const isCoder = m => /coder|code|gpt-oss|deepseek-v4-pro|glm-4\.7$/i.test(m);
  const isStrong = m => /397b|235b|122b|pro|nemotron-3-super|70b|glm-4\.7$|v4-pro/i.test(m);
  const daily = all.slice(0, 16);
  return {
    "日常": { description: "综合日常（部署/保存时自动生成）", candidates: daily },
    "快速": { description: "小杯/Flash 优先", candidates: pick(isFast, daily) },
    "复杂": { description: "大杯优先", candidates: pick(isStrong, daily) },
    "小说": { description: "长文创作（优先稳定中等大杯，减少限流断流）", candidates: pick(isNovel, pick(isStrong, daily)) },
    "代码": { description: "写代码", candidates: pick(isCoder, daily) },
    "识图": { description: "多模态识图", candidates: pick(isVL, daily) },
    daily: { description: "日常（英）", candidates: daily },
    fast: { description: "快速（英）", candidates: pick(isFast, daily) },
    complex: { description: "复杂（英）", candidates: pick(isStrong, daily) },
    novel: { description: "小说（英）", candidates: pick(isStrong, daily) },
    code: { description: "代码（英）", candidates: pick(isCoder, daily) },
    vision: { description: "识图（英）", candidates: pick(isVL, daily) },
    auto: { description: "同日常", candidates: daily },
  };
}

function renderPresetGrid(sel, syncSel){
  const box = document.querySelector(sel);
  if (!box) return;
  box.innerHTML = CHANNEL_PRESETS.map(p => {
    const vpn = p.region === "vpn";
    const tag = vpn ? '<span class="tag-vpn">需 VPN</span>' : '<span class="tag-cn">国内</span>';
    return `<label class="preset-card ${p.defaultOn?"on":""}" data-preset="${esc(p.id)}">
      <div class="row"><div>
        <div class="title"><input type="checkbox" data-preset-check="${esc(p.id)}" ${p.defaultOn?"checked":""}/> ${esc(p.name)} ${tag}</div>
        <div class="note">${esc(p.note)}</div>
      </div></div>
      <div class="url">${esc(p.signup)}</div>
      <div class="acts">
        <a class="btn btn-secondary btn-sm" href="${esc(p.signup)}" target="_blank" rel="noreferrer">打开申请页</a>
        <button class="btn btn-ghost btn-sm" type="button" data-copy-url="${esc(p.signup)}">复制链接</button>
        <button class="btn btn-ghost btn-sm" type="button" data-copy-base="${esc(p.base_url)}">复制 Base URL</button>
      </div>
    </label>`;
  }).join("");
  box.querySelectorAll("[data-preset-check]").forEach(cb => {
    cb.onchange = () => {
      const card = cb.closest(".preset-card");
      if (card) card.classList.toggle("on", cb.checked);
      if (syncSel) syncPresetChecks(sel, syncSel);
    };
  });
  box.querySelectorAll("[data-copy-url]").forEach(b => {
    b.onclick = (e) => { e.preventDefault(); e.stopPropagation(); copyText(b.dataset.copyUrl); };
  });
  box.querySelectorAll("[data-copy-base]").forEach(b => {
    b.onclick = (e) => { e.preventDefault(); e.stopPropagation(); copyText(b.dataset.copyBase); };
  });
}

function syncPresetChecks(fromSel, toSel){
  const src = document.querySelector(fromSel);
  const dst = document.querySelector(toSel);
  if (!src || !dst) return;
  src.querySelectorAll("[data-preset-check]").forEach(cb => {
    const other = dst.querySelector(`[data-preset-check="${cb.dataset.presetCheck}"]`);
    if (!other) return;
    other.checked = cb.checked;
    const card = other.closest(".preset-card");
    if (card) card.classList.toggle("on", cb.checked);
  });
}

function selectedPresetIds(rootSel){
  const root = document.querySelector(rootSel) || document;
  return [...root.querySelectorAll("[data-preset-check]:checked")].map(x => x.dataset.presetCheck);
}

function setPresetFilter(region){
  document.querySelectorAll("[data-preset-check]").forEach(cb => {
    const p = CHANNEL_PRESETS.find(x => x.id === cb.dataset.presetCheck);
    if (!p) return;
    let on = true;
    if (region === "cn") on = p.region === "cn";
    else if (region === "vpn") on = p.region === "vpn";
    else if (region === "none") on = false;
    else if (region === "all") on = true;
    cb.checked = on;
    const card = cb.closest(".preset-card");
    if (card) card.classList.toggle("on", on);
  });
}

function upsertPresetChannel(list, preset){
  const i = findProviderIndex(list, preset.name);
  const shell = normalizeProvider({
    name: preset.name,
    base_url: preset.base_url,
    api_key: "",
    models: (preset.models || []).slice(),
    free_only: !!preset.free_only,
    weight: preset.weight ?? 1,
    enabled: false,
  });
  if (i < 0){ list.push(shell); return "added"; }
  const cur = list[i];
  cur.name = preset.name;
  cur.base_url = preset.base_url;
  // 重新部署时刷新模型列表（保留已有 Key / 启用状态）
  cur.models = (preset.models || []).slice();
  cur.free_only = !!preset.free_only;
  if (cur.weight == null) cur.weight = preset.weight ?? 1;
  return "updated";
}

async function deploySelectedPresets(rootSel){
  const ids = selectedPresetIds(rootSel);
  if (!ids.length){ toast("请先勾选要部署的预设", true); return; }
  const list = (state.providers || []).map(normalizeProvider);
  let added = 0, updated = 0;
  const picked = [];
  for (const id of ids){
    const p = CHANNEL_PRESETS.find(x => x.id === id);
    if (!p) continue;
    picked.push(p);
    const r = upsertPresetChannel(list, p);
    if (r === "added") added += 1; else updated += 1;
  }
  state.providers = list;
  state.dirtyProviders = true;

  
  // 重建路由：按 usage 日志成功率优选（每类最多10个）
  let rebuildMsg = "";
  try {
    const j = await rebuildSmartRoutes(false);
    rebuildMsg = "，已按日志优选 " + ((j.summary || []).length) + " 类路由";
  } catch (_) {
    const rebuilt = rebuildWorkBuddyRoutesFromProviders(list);
    state.routes = Object.assign({}, state.routes || {}, rebuilt);
    rebuildMsg = "，已用渠道列表重建路由（日志优选失败时兜底）";
  }

  const msg = `已写入 ${ids.length} 个渠道（新增 ${added} / 更新 ${updated}）${rebuildMsg}`;

  const el = document.getElementById("presetResult") || document.getElementById("presetResult");
  if (el) el.textContent = msg;
  try{
    await saveProviders(false);
    state.dirtyProviders = false;
    try{
      const rr = await fetch("/api/routers", { method: "PUT", headers: authHeaders(), body: JSON.stringify(state.routes) });
      if (!rr.ok) throw new Error(await rr.text());
    }catch(e){
      toast("渠道已保存，但路由写入失败，请到「路由模型」手动保存", true);
    }
    if (el) el.textContent = msg + " · 已保存";
    toast(msg + "。请到上游渠道粘贴 Key（有 Key 会自动启用）→「保存并同步 WorkBuddy」→ 完全重启 WorkBuddy");
  }catch(_){
    toast(msg + "，请到上游渠道点「保存全部」", true);
  }
  if (typeof renderProviders === "function") renderProviders();
  if (typeof renderRoutes === "function") renderRoutes();
  if (typeof go === "function") go("providers");
}

function bootPresetPicker(){
  renderPresetGrid("#presetGrid", "#presetGrid2");
  renderPresetGrid("#presetGrid2", "#presetGrid");
  const bind = (id, fn) => { const el = document.getElementById(id); if (el) el.onclick = fn; };
  bind("btnPresetCn", () => setPresetFilter("cn"));
  bind("btnPresetVpn", () => setPresetFilter("vpn"));
  bind("btnPresetAll", () => setPresetFilter("all"));
  bind("btnPresetNone", () => setPresetFilter("none"));
  bind("btnPresetCn2", () => setPresetFilter("cn"));
  bind("btnPresetVpn2", () => setPresetFilter("vpn"));
  bind("btnDeployPresets", () => deploySelectedPresets("#presetGrid"));
  bind("btnDeployPresets2", () => deploySelectedPresets("#presetGrid2"));
}

async function saveAndSyncWorkBuddy(){
  try{
    await saveProviders(false);
    try { await rebuildSmartRoutes(false); } catch (_) {}
    const res = await syncWorkBuddy({ silent: true });
    if (!res) {
      toast("渠道已保存，但同步 WorkBuddy 失败（请确认本地 Key 与网关一致）", true);
      return;
    }
    if (!res.ready) {
      toast("渠道已保存并写入 WorkBuddy，但还没有可用上游——请确认至少粘贴了一个有效 API Key", true);
      return;
    }
    toast("已保存并同步 WorkBuddy（" + res.count + " 个模型）。请完全退出并重启 WorkBuddy，且保持本网关运行。");
  }catch(e){
    toast("保存/同步失败：" + (e.message || "未知错误"), true);
  }
}
if ($("#btnSaveSyncWb")) $("#btnSaveSyncWb").onclick = () => saveAndSyncWorkBuddy();

bootPresetPicker();


/* === DASHUAI_ENHANCE_V1 === */
state.routeFilter = state.routeFilter || "";

(function enhanceUI(){
  function ensureNav(){
    // 运维入口已写入静态 HTML；这里重新绑定，避免动态按钮漏绑 onclick
    $$(".nav button[data-page]").forEach(b => {
      b.onclick = () => go(b.dataset.page);
    });
  }

  function ensureHealthBoard(){
    const mon = document.getElementById("page-monitor");
    if (!mon || document.getElementById("healthBoard")) return;
    const panel = document.createElement("div");
    panel.className = "panel";
    panel.innerHTML = `<h3>健康看板</h3>
      <p class="desc">冷却中的模型、失败原因与预计恢复（本页约 5 秒刷新）。</p>
      <div id="healthBoard" class="empty">打开本页后自动加载</div>`;
    mon.appendChild(panel);
  }

  function ensureUsageExtras(){
    const page = document.getElementById("page-usage");
    if (!page) return;
    const headActions = page.querySelector(".head .inline");
    if (headActions && !document.getElementById("btnExportCsv")){
      const b = document.createElement("button");
      b.className = "btn btn-secondary btn-sm";
      b.type = "button";
      b.id = "btnExportCsv";
      b.textContent = "导出 CSV";
      headActions.insertBefore(b, headActions.firstChild);
      b.onclick = () => window.open(`/api/usage.csv?days=${state.usageDays||1}`, "_blank");
    }
    const ov = document.getElementById("usageOverview");
    if (ov && !document.getElementById("usageDayBars")){
      const bars = document.createElement("div");
      bars.className = "bars";
      bars.id = "usageDayBars";
      bars.innerHTML = `<div class="empty" style="margin:auto">暂无趋势</div>`;
      ov.insertAdjacentElement("afterend", bars);
    }
    const callBody = document.getElementById("callLogBody");
    const callPanel = callBody && callBody.closest(".panel");
    if (callPanel && !document.getElementById("callRouteFilter")){
      const row = document.createElement("div");
      row.className = "filter-row";
      row.innerHTML = `<span style="color:var(--muted);font-size:12px">路由筛选</span>
        <select id="callRouteFilter">
          <option value="">全部</option>
          <option>日常</option><option>快速</option><option>复杂</option>
          <option>小说</option><option>代码</option><option>识图</option>
          <option>翻译</option><option>总结</option><option>推理</option>
          <option>长文</option><option>Agent</option>
          <option>daily</option><option>fast</option><option>complex</option>
          <option>novel</option><option>code</option>
        </select>`;
      const tableWrap = callPanel.querySelector(".table-wrap") || callBody.closest("div");
      callPanel.insertBefore(row, tableWrap);
      document.getElementById("callRouteFilter").onchange = (ev) => {
        state.routeFilter = ev.target.value || "";
        loadCallLog();
      };
      const thead = callPanel.querySelector("thead tr");
      if (thead && thead.children.length <= 4){
        thead.innerHTML = `<th>时间</th><th>状态</th><th>路由</th><th>渠道 / 模型</th><th>Tokens</th><th>延迟</th>`;
      }
    }
  }

  function wireOpsHandlers(){
    if (wireOpsHandlers._done) return;
    const on = document.getElementById("btnAutostartOn");
    const off = document.getElementById("btnAutostartOff");
    const backup = document.getElementById("btnBackup");
    const refresh = document.getElementById("btnRefreshBackups");
    const diag = document.getElementById("btnWbDiagnose");
    const sync = document.getElementById("btnSyncWbOps");
    if (!on || !off || !backup || !refresh || !diag || !sync) return;
    wireOpsHandlers._done = true;
    on.onclick = async () => {
      try{
        const r = await fetch("/api/ops/autostart", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({enabled:true})});
        if (!r.ok) return toast("开启失败", true);
        toast("已开启开机自启"); loadOpsPage();
      }catch(_){ toast("开启失败", true); }
    };
    off.onclick = async () => {
      try{
        const r = await fetch("/api/ops/autostart", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({enabled:false})});
        if (!r.ok) return toast("关闭失败", true);
        toast("已关闭开机自启"); loadOpsPage();
      }catch(_){ toast("关闭失败", true); }
    };
    backup.onclick = async () => {
      try{
        const r = await fetch("/api/ops/backup", {method:"POST", headers: authHeaders()});
        if (!r.ok) return toast("备份失败：检查本地 Key", true);
        toast("备份完成"); refreshBackupList();
      }catch(_){ toast("备份失败", true); }
    };
    refresh.onclick = () => refreshBackupList();
    diag.onclick = async () => {
      const box = document.getElementById("wbDiagnoseBox");
      if (!box) return;
      box.textContent = "诊断中…";
      try{
        const r = await fetch("/api/integrations/workbuddy/diagnose");
        const j = await r.json();
        const issues = (j.issues||[]).map(x=>`• ${esc(x)}`).join("<br>") || "无问题";
        const tips = (j.tips||[]).map(x=>`• ${esc(x)}`).join("<br>");
        box.innerHTML = `<div>${j.ok?"✅ 通过":"⚠️ 发现问题"} · 大帅条目 ${j.ours||0}</div>
          <div style="margin-top:8px;font-size:12px">${issues}</div>
          <div style="margin-top:8px;color:var(--muted);font-size:12px">${tips}</div>`;
      }catch(_){ box.textContent = "诊断失败"; }
    };
    sync.onclick = () => {
      if ($("#btnSyncWb")) $("#btnSyncWb").click();
      else if ($("#btnSyncWbTop")) $("#btnSyncWbTop").click();
      else toast("未找到同步按钮，请到一键接入页操作", true);
    };
  }

  function ensureOpsPage(){
    // 页面已在静态 HTML；只负责绑定按钮
    wireOpsHandlers();
  }

  async function bootstrapLocalKey(){
    try{
      const r = await fetch("/api/bootstrap");
      if (!r.ok) return;
      const j = await r.json();
      const key = String(j.local_api_key || "").trim();
      if (!key) return;
      const cur = String(state.localKey || "").trim();
      const isDefault = !cur || cur.includes("change-me") || cur === "sk-local-change-me";
      if (isDefault || cur !== key){
        state.localKey = key;
        localStorage.setItem("dashuai_local_key", key);
        if ($("#localKey")) $("#localKey").value = key;
        if ($("#homeKey")) $("#homeKey").textContent = key;
      }
    }catch(_){}
  }

  async function loadHealthBoard(){
    const box = $("#healthBoard");
    if (!box) return;
    try{
      const r = await fetch("/api/health-board");
      if (!r.ok) throw new Error("hb");
      const j = await r.json();
      const cooling = j.cooling || [];
      const fails = j.recent_failures || [];
      if (!cooling.length && !fails.length){
        box.innerHTML = `<div class="empty">当前没有冷却中的模型，也没有最近失败。</div>`;
        return;
      }
      let html = "";
      if (cooling.length){
        html += `<div style="margin-bottom:8px"><strong>冷却中 (${cooling.length})</strong></div>`;
        html += `<div class="table-wrap"><table><thead><tr><th>渠道</th><th>模型</th><th>剩余</th><th>原因</th></tr></thead><tbody>`;
        html += cooling.map(c => `<tr>
          <td>${esc(c.provider)}</td><td>${esc(c.model)}</td>
          <td>${fmtNum(c.cooldown_remaining_sec)}s</td>
          <td><span class="chip bad">${esc(c.error_kind||"cooldown")}</span> ${esc(String(c.last_error||"").slice(0,90))}</td>
        </tr>`).join("");
        html += `</tbody></table></div>`;
      }
      if (fails.length){
        html += `<div style="margin:12px 0 8px"><strong>最近失败</strong></div>`;
        html += `<div class="table-wrap"><table><thead><tr><th>时间</th><th>类型</th><th>渠道/模型</th><th>错误</th></tr></thead><tbody>`;
        html += fails.map(f => {
          const t = f.ts ? new Date(f.ts*1000).toLocaleTimeString() : "";
          return `<tr><td>${esc(t)}</td><td>${esc(f.kind||"")}</td>
            <td>${esc(f.provider)} / ${esc(f.model)}</td>
            <td style="color:#fecaca;font-size:12px">${esc(String(f.error||"").slice(0,100))}</td></tr>`;
        }).join("");
        html += `</tbody></table></div>`;
      }
      box.innerHTML = html;
    }catch(_){
      box.innerHTML = `<div class="empty">健康看板加载失败</div>`;
    }
  }

  async function loadOpsPage(){
    try{
      const r = await fetch("/api/ops/autostart");
      const j = r.ok ? await r.json() : {};
      const el = $("#autostartStatus");
      if (el) el.textContent = j.enabled ? "已开启开机自启" : (j.supported === false ? "当前系统不支持" : "未开启");
    }catch(_){}
    await refreshBackupList();
    await refreshUsageArchiveList();
  }

  async function refreshUsageArchiveList(){
    const box = $("#usageArchiveList");
    if (!box) return;
    try{
      const r = await fetch("/api/ops/usage/archives");
      const j = await r.json();
      const items = j.items || [];
      if (!items.length){ box.innerHTML = `<div class="empty">暂无归档</div>`; return; }
      box.innerHTML = items.map(it =>
        `<div style="font-size:12px;padding:4px 0;color:var(--muted)">${esc(it.name)} · ${((it.bytes||0)/1024).toFixed(1)} KB</div>`
      ).join("");
    }catch(_){ box.innerHTML = `<div class="empty">归档列表加载失败</div>`; }
  }

  if ($("#btnUsageArchive")) $("#btnUsageArchive").onclick = async () => {
    if (!confirm("归档当前 usage.jsonl 并开始新文件？")) return;
    const r = await fetch("/api/ops/usage/archive", { method:"POST", headers: authHeaders() });
    const j = await r.json().catch(()=>({}));
    if (!r.ok) return toast("归档失败", true);
    toast(j.message || "已归档用量日志");
    refreshUsageArchiveList();
  };
  if ($("#btnUsageClear")) $("#btnUsageClear").onclick = async () => {
    if (!confirm("清空当前用量并归档？此操作不可撤销。")) return;
    const r = await fetch("/api/ops/usage/clear", { method:"POST", headers: authHeaders() });
    if (!r.ok) return toast("清空失败", true);
    toast("已清空并归档");
    refreshUsageArchiveList();
    loadUsage();
  };
  if ($("#btnUsageArchList")) $("#btnUsageArchList").onclick = () => refreshUsageArchiveList();

  if ($("#btnFlushUsage")) $("#btnFlushUsage").onclick = async () => {
    const r = await fetch("/api/license/flush-usage", { method:"POST", headers: authHeaders() });
    const j = await r.json().catch(()=>({}));
    if (!r.ok) return toast("上报失败", true);
    toast(j.message || "已尝试上报");
    loadLicenseStatus(true);
  };

  async function refreshBackupList(){
    const box = $("#backupList");
    if (!box) return;
    try{
      const r = await fetch("/api/ops/backups");
      const j = await r.json();
      const items = j.items || [];
      if (!items.length){ box.innerHTML = `<div class="empty">暂无备份</div>`; return; }
      box.innerHTML = items.map(it => `<div class="inline" style="margin:6px 0;justify-content:space-between;gap:8px">
        <span style="font-size:12px">${esc(it.name)} · ${((it.bytes||0)/1024).toFixed(1)} KB</span>
        <button class="btn btn-ghost btn-sm" type="button" data-restore="${esc(it.name)}">还原</button>
      </div>`).join("");
    }catch(_){ box.innerHTML = `<div class="empty">备份列表加载失败</div>`; }
  }

  document.body.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-restore]");
    if (!btn) return;
    if (!confirm("确认用该备份覆盖当前配置？")) return;
    const r = await fetch("/api/ops/restore", {
      method:"POST", headers: authHeaders(), body: JSON.stringify({name: btn.dataset.restore})
    });
    if (!r.ok) return toast("还原失败", true);
    toast("已还原，建议刷新页面");
  });

  const _renderUsage = renderUsage;
  renderUsage = function(data){
    const t = data.total || {};
    const cards = [
      { label: "输入 Token", value: t.pt },
      { label: "输出 Token", value: t.ct },
      { label: "合计 Token", value: t.tt },
      { label: "客户端请求", value: t.client_requests ?? t.requests },
      { label: "上游调用", value: t.upstream_attempts ?? t.requests },
      { label: "成功率", value: (t.success_rate != null ? (t.success_rate + "%") : "—"), raw: true },
      { label: "平均延迟", value: (t.avg_latency_ms != null ? (Math.round(t.avg_latency_ms) + " ms") : "—"), raw: true },
    ];
    const ov = $("#usageOverview");
    if (ov){
      ov.innerHTML = cards.map(c =>
        `<div class="stat-card"><div class="k">${c.label}</div><div class="v">${c.raw ? c.value : fmtNum(c.value)}</div></div>`
      ).join("");
    }
    const days = data.by_day || [];
    const bars = $("#usageDayBars");
    if (bars){
      if (!days.length){
        bars.innerHTML = `<div class="empty" style="margin:auto">暂无按日趋势</div>`;
      } else {
        const maxTt = Math.max(1, ...days.map(d => Number(d.tt)||0));
        bars.innerHTML = days.slice(-14).map(d => {
          const h = Math.max(4, Math.round(((Number(d.tt)||0)/maxTt)*100));
          const bad = (Number(d.fail)||0) > (Number(d.ok)||0);
          return `<div class="b ${bad?"bad":""}" style="height:${h}%" title="${esc(d.day)} · ${fmtNum(d.tt)}"><i>${esc(String(d.day).slice(5))}</i></div>`;
        }).join("");
      }
    }
    const rows = data.by_model || [];
    const body = $("#usageBody");
    if (body){
      const table = body.closest("table");
      const th = table && table.querySelector("thead tr");
      if (th && th.children.length < 7){
        th.innerHTML = `<th>渠道 / 模型</th><th>上游调用</th><th>成功/失败</th><th>输入</th><th>输出</th><th>合计</th><th>备注</th>`;
      }
      body.innerHTML = rows.length
        ? rows.map(r => `<tr>
            <td><span class="badge">${esc(r.provider || "?")}</span>${esc(r.model || "?")}</td>
            <td>${fmtNum(r.requests)}</td>
            <td>${fmtNum(r.ok)} / ${fmtNum(r.fail||0)}</td>
            <td>${fmtNum(r.pt)}</td>
            <td>${fmtNum(r.ct)}</td>
            <td>${fmtNum(r.tt)}</td>
            <td style="font-size:11px;color:var(--muted)">${r.estimated ? "≈估算" : ""}</td>
          </tr>`).join("")
        : `<tr><td colspan="7" style="color:var(--muted)">暂无消耗记录</td></tr>`;
    }
    const routeBox = $("#routeSuccessCards");
    if (routeBox) {
      const picks = ["小说", "日常", "快速", "Agent"];
      const byRoute = data.by_route || [];
      routeBox.innerHTML = picks.map(name => {
        const r = byRoute.find(x => x.route === name);
        if (!r || !r.requests) return `<div class="stat-card"><div class="k">${esc(name)}</div><div class="v">—</div></div>`;
        const rate = Math.round(((r.ok || 0) * 100) / r.requests);
        const bad = name === "小说" && rate < 70;
        return `<div class="stat-card" style="${bad ? "border-color:rgba(239,68,68,.4)" : ""}"><div class="k">${esc(name)}</div><div class="v">${rate}%</div><div class="h" style="font-size:11px;color:var(--muted)">${r.ok || 0}/${r.requests} 成功</div></div>`;
      }).join("");
    }
  };

  const _loadCallLog = loadCallLog;
  loadCallLog = async function(){
    try{
      const q = state.routeFilter ? `&route=${encodeURIComponent(state.routeFilter)}` : "";
      const r = await fetch(`/api/call-log?limit=100${q}`);
      if (!r.ok) throw new Error("call-log");
      const data = await r.json();
      const tbody = $("#callLogBody");
      if (!tbody) return;
      if (!data || !data.length){
        tbody.innerHTML = `<tr><td colspan="6" style="color:var(--muted)">暂无调用记录</td></tr>`;
        return;
      }
      tbody.innerHTML = data.slice().reverse().map(d => {
        const ok = d.status === "ok";
        const err = d.error ? ` <span style="font-size:11px;color:#fecaca">(${esc(d.error)})</span>` : "";
        return `<tr>
          <td style="color:var(--muted);font-size:12px">${esc(d.time || "")}</td>
          <td>${ok ? '<span class="chip ok">成功</span>' : '<span class="chip bad">失败</span>'}${err}</td>
          <td>${esc(d.route || "—")}</td>
          <td><span class="badge">${esc(d.provider || "-")}</span>${esc(d.model || "-")}</td>
          <td style="font-variant-numeric:tabular-nums;color:var(--muted)">${d.tokens ? fmtNum(d.tokens) : "—"}</td>
          <td style="color:var(--muted)">${d.latency_ms != null ? Math.round(d.latency_ms)+"ms" : "—"}</td>
        </tr>`;
      }).join("");
    }catch(_){}
  };

  const _go = go;
  go = function(page){
    _go(page);
    if (page === "monitor") loadHealthBoard();
    if (page === "ops") loadOpsPage();
    if (page === "usage") ensureUsageExtras();
  };

  ensureNav();
  ensureHealthBoard();
  ensureUsageExtras();
  ensureOpsPage();
  bootstrapLocalKey().then(() => {});

  setInterval(() => {
    if ($("#page-monitor") && $("#page-monitor").classList.contains("active")) loadHealthBoard();
  }, 5000);

  // ---- license / shop ----
  const lic = { remote: null, pollTimer: null, selectedPriceId: null, agreed: localStorage.getItem("dashuai_disclaimer_ok") === "1" };

  function rememberedUsername(){
    return (localStorage.getItem("dashuai_username") || "").trim();
  }
  function rememberUsername(name){
    const n = String(name || "").trim();
    if (n) localStorage.setItem("dashuai_username", n);
  }

  function fmtRemain(licSnap){
    if (!licSnap) return "权益：—";
    if (licSnap.require_license === false && !licSnap.logged_in) return "开发模式（未强制授权）";
    if (!licSnap.logged_in) return "未登录";
    if (!licSnap.valid) return licSnap.message || "未激活";
    const parts = [];
    if (licSnap.time_unlimited) parts.push("不限时");
    else if (licSnap.expire_at) parts.push("至 " + String(licSnap.expire_at).slice(0, 16));
    if (licSnap.token_unlimited) parts.push("Token 不限");
    else if (licSnap.token_remaining != null) {
      const n = Number(licSnap.token_remaining);
      const q = Number(licSnap.token_quota || 0);
      parts.push("剩余 " + (n >= 1e8 ? (n/1e8).toFixed(1)+"亿" : fmtNum(n)) + " Token");
      if (q > 0 && n / q < 0.1) parts.push("⚠ 余量不足");
    }
    if (licSnap.pending_usage_count > 0) parts.push("待上报 " + licSnap.pending_usage_count);
    if (licSnap.plan_label) parts.unshift(licSnap.plan_label);
    return parts.join(" · ") || "已激活";
  }

  function paintAccount(snap){
    const logged = !!(snap && snap.logged_in);
    const name = (snap && snap.username) || rememberedUsername() || "";
    const ap = $("#accountPill");
    if (ap) ap.textContent = logged ? ("账号：" + (name || "已登录")) : "未登录";
    const chip = $("#shopAccountChip");
    if (chip) chip.textContent = logged ? ("当前：" + (name || "已登录")) : "未登录";
    const showBtn = logged || !!(snap && snap.require_license !== false);
    ["btnLogoutTop","btnRelogin","btnLogout","btnReloginShop"].forEach(id => {
      const el = $("#"+id);
      if (!el) return;
      if (id.startsWith("btnLogout")) el.style.display = logged ? "" : "none";
      else el.style.display = showBtn ? "" : "none";
    });
  }

  function paintLicense(snap){
    const pill = $("#licensePill");
    if (pill) {
      pill.textContent = fmtRemain(snap);
      const low = snap && !snap.token_unlimited && snap.token_quota > 0 && snap.token_remaining != null
        && Number(snap.token_remaining) / Number(snap.token_quota) < 0.1;
      pill.style.color = low ? "#fecaca" : "";
    }
    const pendingChip = $("#pendingUsageChip");
    if (pendingChip) {
      const n = snap && snap.pending_usage_count != null ? Number(snap.pending_usage_count) : 0;
      pendingChip.textContent = n > 0 ? ("待上报 " + n + " 条") : "待上报：无";
      pendingChip.className = n > 0 ? "chip bad" : "chip";
    }
    state.license = snap;
    paintAccount(snap);
  }
  window.paintLicense = paintLicense;

  async function loadLicenseStatus(refresh){
    try{
      const r = await fetch("/api/license/status" + (refresh ? "?refresh=1" : ""));
      const j = await r.json();
      if (j && j.username) rememberUsername(j.username);
      paintLicense(j);
      return j;
    }catch(_){ return null; }
  }

  async function doLogout(){
    try { await fetch("/api/account/logout", { method:"POST" }); } catch(_){}
    paintLicense({ logged_in: false, valid: false, require_license: true, message: "已退出" });
    toast("已退出登录");
    await runLicenseGate();
  }

  async function doRelogin(){
    try { await fetch("/api/account/logout", { method:"POST" }); } catch(_){}
    paintLicense({ logged_in: false, valid: false, require_license: true, message: "请重新登录" });
    toast("请重新登录");
    lic.agreed = true; // 免责声明已同意过，直接进登录
    gateAuth();
  }

  async function loadRemoteBootstrap(){
    try{
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 10000);
      const r = await fetch("/api/remote/bootstrap", { signal: ctrl.signal });
      clearTimeout(t);
      const j = await r.json();
      lic.remote = j;
      const bar = $("#announceBar");
      if (bar && j.announcement){
        bar.textContent = j.announcement;
        bar.classList.add("show");
      }
      if ($("#guideStepsText")) $("#guideStepsText").textContent = j.guideSteps || "";
      if ($("#apiKeyGuideText")) $("#apiKeyGuideText").textContent = j.apiKeyGuide || "";
      if ($("#disclaimerText")) $("#disclaimerText").textContent = j.disclaimer || "";
      if ($("#navVer") && j.latestVersion) $("#navVer").textContent = "v" + (state.overview && state.overview.version ? state.overview.version : j.version || "") + " / 远端 " + j.latestVersion;
      return j;
    }catch(_){ return null; }
  }

  function showGate(html){
    const g = $("#licenseGate");
    const box = $("#gateBox");
    if (!g || !box) return;
    box.innerHTML = html;
    g.classList.add("show");
  }
  function hideGate(){ const g = $("#licenseGate"); if (g) g.classList.remove("show"); }

  function gateDisclaimer(){
    const text = (lic.remote && lic.remote.disclaimer) || "本软件仅供个人学习与合法用途。";
    showGate(`<h2>免责声明</h2><p class="desc">${esc(text)}</p>
      <label class="switch" style="margin-bottom:14px"><input type="checkbox" id="agreeChk" /> 我已阅读并同意</label>
      <button class="btn btn-primary" type="button" id="btnAgree">继续</button>`);
    $("#btnAgree").onclick = () => {
      if (!$("#agreeChk").checked){ toast("请先勾选同意", true); return; }
      localStorage.setItem("dashuai_disclaimer_ok", "1");
      lic.agreed = true;
      gateAuth();
    };
  }

  function gateAuth(){
    const remembered = rememberedUsername();
    showGate(`<h2>登录大帅网关</h2><p class="desc">普通用户账号，与卡密绑定。登录状态会保存在本机，下次打开自动保持。</p>
      <div class="gate-tabs">
        <button class="btn btn-primary btn-sm" type="button" id="tabLogin">登录</button>
        <button class="btn btn-ghost btn-sm" type="button" id="tabReg">注册</button>
      </div>
      <div class="field"><label>用户名</label><input id="gateUser" value="${esc(remembered)}" autocomplete="username" /></div>
      <div class="field"><label>密码</label><input id="gatePass" type="password" autocomplete="current-password" /></div>
      <div class="field" id="gatePass2Wrap" style="display:none"><label>确认密码</label><input id="gatePass2" type="password" autocomplete="new-password" /></div>
      <label class="switch" style="margin:8px 0 14px"><input type="checkbox" id="rememberUser" ${remembered ? "checked" : "checked"} /> 记住用户名</label>
      <button class="btn btn-primary" type="button" id="btnGateSubmit">登录</button>`);
    let mode = "login";
    $("#tabLogin").onclick = () => { mode="login"; $("#gatePass2Wrap").style.display="none"; $("#btnGateSubmit").textContent="登录"; $("#tabLogin").className="btn btn-primary btn-sm"; $("#tabReg").className="btn btn-ghost btn-sm"; };
    $("#tabReg").onclick = () => { mode="reg"; $("#gatePass2Wrap").style.display=""; $("#btnGateSubmit").textContent="注册"; $("#tabReg").className="btn btn-primary btn-sm"; $("#tabLogin").className="btn btn-ghost btn-sm"; };
    const passEl = $("#gatePass");
    if (passEl) passEl.focus();
    $("#btnGateSubmit").onclick = async () => {
      const username = $("#gateUser").value.trim();
      const password = $("#gatePass").value;
      if (!username || !password){ toast("请填写用户名和密码", true); return; }
      const btn = $("#btnGateSubmit");
      const old = btn ? btn.textContent : "";
      if (btn){ btn.disabled = true; btn.textContent = "请稍候…"; }
      try{
        if (mode === "reg"){
          const confirmPassword = $("#gatePass2").value;
          if (password !== confirmPassword){ toast("两次密码不一致", true); return; }
          const rr = await fetch("/api/account/register", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ username, password, confirmPassword }) });
          const jj = await rr.json().catch(()=>({}));
          if (!rr.ok) throw new Error(errText(jj, "注册失败"));
          toast("注册成功，正在登录…");
        }
        const r = await fetch("/api/account/login", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ username, password }) });
        const j = await r.json().catch(()=>({}));
        if (!r.ok) throw new Error(errText(j, "登录失败（用户名或密码错误）"));
        if ($("#rememberUser") && $("#rememberUser").checked) rememberUsername(username);
        else localStorage.removeItem("dashuai_username");
        paintLicense(j.license || await loadLicenseStatus(true));
        await afterLoginGate();
      }catch(e){
        toast(errText(e, e && e.message) || "登录失败", true);
      }finally{
        if (btn){ btn.disabled = false; btn.textContent = old || (mode==="reg"?"注册":"登录"); }
      }
    };
  }

  async function afterLoginGate(){
    const snap = await loadLicenseStatus(true);
    if (snap && snap.valid){ hideGate(); toast("已激活，可以使用"); return; }
    gateActivate();
  }

  function gateActivate(){
    showGate(`<h2>激活权益</h2><p class="desc">购买套餐或输入已有卡密。一卡密仅绑定一个账号。</p>
      <div class="gate-tabs">
        <button class="btn btn-primary btn-sm" type="button" id="tabBuy">购买</button>
        <button class="btn btn-ghost btn-sm" type="button" id="tabCode">输入卡密</button>
      </div>
      <div id="gateActBody"></div>
      <div style="margin-top:12px"><button class="btn btn-ghost btn-sm" type="button" id="btnGateLogout">退出登录</button></div>`);
    const body = $("#gateActBody");
    const showBuy = async () => {
      body.innerHTML = `<div class="field"><label>收货邮箱</label><input id="gateEmail" type="email" placeholder="用于接收卡密" /></div>
        <div class="sku-grid" id="gateSku"><div class="empty">加载中…</div></div><div class="pay-box" id="gatePay" style="display:none"></div>`;
      await renderSkus("#gateSku", "#gatePay", true);
    };
    const showCode = () => {
      body.innerHTML = `<div class="field"><label>卡密</label><input id="gateCard" /></div>
        <button class="btn btn-primary" type="button" id="btnGateRedeem">激活</button>`;
      $("#btnGateRedeem").onclick = () => doRedeem($("#gateCard").value, true);
    };
    $("#tabBuy").onclick = () => { $("#tabBuy").className="btn btn-primary btn-sm"; $("#tabCode").className="btn btn-ghost btn-sm"; showBuy(); };
    $("#tabCode").onclick = () => { $("#tabCode").className="btn btn-primary btn-sm"; $("#tabBuy").className="btn btn-ghost btn-sm"; showCode(); };
    $("#btnGateLogout").onclick = () => doLogout();
    showBuy();
  }

  async function doRedeem(code, fromGate){
    code = String(code || "").trim();
    if (!code){ toast("请输入卡密", true); return; }
    try{
      const r = await fetch("/api/license/redeem", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ cardCode: code }) });
      const j = await r.json().catch(()=>({}));
      if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : (j.detail && j.detail.message) || "激活失败");
      paintLicense(j.license || await loadLicenseStatus(true));
      toast("激活成功");
      if (fromGate) hideGate();
    }catch(e){ toast(e.message || "激活失败", true); }
  }

  function isTokenSku(p, features, types){
    const f = (features || []).find(x => x.id === p.featureId || x.id === p.feature_id);
    const t = (types || []).find(x => x.id === p.typeId || x.id === p.type_id);
    const code = String((f && (f.featureCode || f.feature_code)) || "").toUpperCase();
    const tcode = String((t && (t.typeCode || t.type_code)) || "").toUpperCase();
    const tname = String((t && (t.typeName || t.type_name)) || "");
    if (tcode.includes("TOKEN") || code.startsWith("TOKENS_") || /token/i.test(tname)) return true;
    return false;
  }

  function skuLabel(p, features, types){
    const f = (features || []).find(x => x.id === p.featureId || x.id === p.feature_id);
    const t = (types || []).find(x => x.id === p.typeId || x.id === p.type_id);
    const featureName = (f && (f.featureName || f.feature_name)) || "";
    const typeName = (t && (t.typeName || t.type_name)) || "";
    const token = isTokenSku(p, features, types);
    if (token){
      // Token 包：只显示额度名 + 价格，不显示中间那行代码
      return { title: featureName || typeName || p.cardType || "Token包", sub: "", price: p.price };
    }
    // 时间卡：主标题用功能名，中间显示天卡/月卡/季卡/年卡
    return {
      title: featureName || typeName || p.cardType || "时长套餐",
      sub: typeName || "",
      price: p.price
    };
  }

  async function renderSkus(gridSel, paySel, fromGate){
    const grid = typeof gridSel === "string" ? $(gridSel) : gridSel;
    const pay = typeof paySel === "string" ? $(paySel) : paySel;
    if (!grid) return;
    try{
      const r = await fetch("/api/shop/catalog");
      const j = await r.json();
      const prices = (j.prices || []).filter(p => p.enabled !== false);
      if (!prices.length){ grid.innerHTML = `<div class="empty">暂无商品（请确认授权服务已配置大帅网关 SKU）</div>`; return; }
      grid.innerHTML = prices.map(p => {
        const L = skuLabel(p, j.features, j.types);
        const subHtml = L.sub ? `<div style="color:var(--muted);font-size:12px">${esc(L.sub)}</div>` : "";
        return `<div class="sku" data-price-id="${p.id}"><div>${esc(L.title)}</div>${subHtml}<div class="price">¥${esc(L.price)}</div></div>`;
      }).join("");
      grid.querySelectorAll(".sku").forEach(el => {
        el.onclick = () => createOrder(Number(el.dataset.priceId), pay, fromGate);
      });
    }catch(e){
      grid.innerHTML = `<div class="empty">加载失败：${esc(e.message||"")}</div>`;
    }
  }

  async function createOrder(priceId, payBox, fromGate){
    if (!payBox) return;
    payBox.style.display = "block";
    payBox.innerHTML = `<div class="empty">正在创建订单…</div>`;
    try{
      const email = ($("#buyerEmail") && $("#buyerEmail").value.trim())
        || ($("#gateEmail") && $("#gateEmail").value.trim())
        || "";
      if (!email){ payBox.innerHTML = `<div class="empty" style="color:#fecaca">请先填写收货邮箱</div>`; toast("请填写收货邮箱", true); return; }
      const r = await fetch("/api/shop/order", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ priceId, buyerEmail: email }) });
      const j = await r.json().catch(()=>({}));
      if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : (j.detail && j.detail.message) || "下单失败");
      const payUrl = j.payUrl || j.pay_url || "";
      const orderNo = j.orderNo || j.order_no || "";
      const amount = j.amount;
      let qr = "";
      if (payUrl){
        qr = `<img alt="微信收款码" src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(payUrl)}" />`;
      }
      payBox.innerHTML = `<div>${qr}</div><p>请使用微信扫码支付</p>
        <p class="qr-fallback">订单号：${esc(orderNo)}　金额：¥${esc(amount)}</p>
        <p class="qr-fallback">${esc(payUrl)}</p>
        <button class="btn btn-secondary btn-sm" type="button" id="btnPollPay">我已支付</button>`;
      const poll = async () => {
        const qr2 = await fetch(`/api/shop/order/${encodeURIComponent(orderNo)}${amount!=null?`?verifyAmount=${encodeURIComponent(amount)}`:""}`);
        const oj = await qr2.json().catch(()=>({}));
        if (String(oj.status||"").toUpperCase() === "PAID"){
          const rr = await fetch(`/api/shop/order/${encodeURIComponent(orderNo)}/redeem`, { method:"POST" });
          const rj = await rr.json().catch(()=>({}));
          if (rj.ok){
            paintLicense(rj.license || await loadLicenseStatus(true));
            toast("支付成功并已激活");
            if (fromGate) hideGate();
            if (lic.pollTimer) clearInterval(lic.pollTimer);
            return true;
          }
          toast(rj.message || "已支付，请手动输入卡密激活", true);
          const code = oj.cardCode || oj.card_code;
          if (code) await doRedeem(code, fromGate);
          return true;
        }
        return false;
      };
      $("#btnPollPay").onclick = () => poll();
      if (lic.pollTimer) clearInterval(lic.pollTimer);
      let n = 0;
      lic.pollTimer = setInterval(async () => {
        n++;
        if (await poll() || n > 60) clearInterval(lic.pollTimer);
      }, 3000);
    }catch(e){
      payBox.innerHTML = `<div class="empty" style="color:#fecaca">${esc(e.message||"下单失败")}</div>`;
    }
  }

  async function runLicenseGate(){
    await loadRemoteBootstrap();
    // 先读本地缓存（不强制远端），有会话即可跳过登录门；再后台刷新
    let snap = await loadLicenseStatus(false);
    paintLicense(snap);
    if (!snap || snap.require_license === false){
      hideGate();
      loadLicenseStatus(true);
      return;
    }
    if (lic.remote && lic.remote.maintenanceEnabled){
      showGate(`<h2>维护中</h2><p class="desc">${esc(lic.remote.maintenanceMessage || "服务维护中，请稍后再试")}</p>`);
      return;
    }
    if (!lic.agreed){ gateDisclaimer(); return; }
    if (!snap.logged_in){ gateAuth(); return; }
    if (!snap.valid){
      // 已登录但权益无效：先试刷新远端，再决定是否进激活页
      snap = await loadLicenseStatus(true) || snap;
      paintLicense(snap);
      if (!snap.valid){ gateActivate(); return; }
    } else {
      // 后台刷新权益，不挡界面
      loadLicenseStatus(true).then(s => { if (s) paintLicense(s); });
    }
    hideGate();
  }

  if ($("#btnRedeemCard")) $("#btnRedeemCard").onclick = () => doRedeem($("#cardCodeInput") && $("#cardCodeInput").value);
  if ($("#btnLogout")) $("#btnLogout").onclick = () => doLogout();
  if ($("#btnLogoutTop")) $("#btnLogoutTop").onclick = () => doLogout();
  if ($("#btnRelogin")) $("#btnRelogin").onclick = () => doRelogin();
  if ($("#btnReloginShop")) $("#btnReloginShop").onclick = () => doRelogin();
  if ($("#btnCheckUpdate")) $("#btnCheckUpdate").onclick = async () => {
    try{
      const r = await fetch("/api/update/check");
      const j = await r.json().catch(()=>({}));
      if (!r.ok) throw new Error("check failed");
      if (!j.update_available) {
        toast("已是最新版本 " + (j.latest_version || j.local_version));
        return;
      }
      let msg = "发现新版本 " + j.latest_version + "（当前 " + j.local_version + "）";
      if (j.download_sha256) msg += "\nSHA256: " + j.download_sha256.slice(0, 16) + "…";
      toast(msg + (j.download_url ? "，正在打开下载页" : ""));
      if (j.download_url) window.open(j.download_url, "_blank");
    }catch(_){
      const j = await loadRemoteBootstrap();
      const local = (state.overview && state.overview.version) || (j && j.version) || "";
      const latest = j && j.latestVersion;
      if (!latest){ toast("无法获取远端版本"); return; }
      if (String(local) === String(latest)) toast("已是最新版本 " + latest);
      else {
        toast("发现新版本 " + latest + (j.downloadUrl ? "，正在打开下载页" : ""));
        if (j.downloadUrl) window.open(j.downloadUrl, "_blank");
      }
    }
  };

  const _go2 = go;
  go = function(page){
    _go2(page);
    if (page === "shop") renderSkus("#skuGrid", "#payBox", false);
    if (page === "guide") loadRemoteBootstrap();
  };

  runLicenseGate().then(() => {});
  setInterval(() => { loadLicenseStatus(true); }, 60000);
})();

