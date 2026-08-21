# -*- coding: utf-8 -*-
"""Generate a clean, working web/index.html for Dashuai Gateway."""
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "index.html"

HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>大帅网关</title>
<style>
:root{--bg:#0b1220;--panel:#121a2b;--panel2:#172235;--line:rgba(148,163,184,.16);--text:#e8eef9;--muted:#93a0b8;--primary:#3b82f6;--primary2:#2563eb;--ok:#22c55e;--warn:#f59e0b;--danger:#ef4444;--radius:14px;--nav:200px}
*{box-sizing:border-box}html,body{height:100%;margin:0}
body{color:var(--text);font:14px/1.5 "Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);overflow:hidden}
button,input,textarea,select{font:inherit}button{cursor:pointer}
.app{display:grid;grid-template-columns:var(--nav) 1fr;height:100vh}
.nav{background:linear-gradient(180deg,#0f172a,#0b1220);border-right:1px solid var(--line);padding:14px 10px;display:flex;flex-direction:column;gap:6px}
.brand{display:flex;gap:10px;align-items:center;padding:8px 10px 16px}
.logo{width:36px;height:36px;border-radius:10px;display:grid;place-items:center;background:linear-gradient(145deg,#60a5fa,#2563eb);font-weight:700;box-shadow:0 8px 18px rgba(37,99,235,.35)}
.brand h1{margin:0;font-size:15px}.brand p{margin:2px 0 0;color:var(--muted);font-size:11px}
.nav button{width:100%;text-align:left;border:0;background:transparent;color:var(--muted);border-radius:10px;padding:10px 12px}
.nav button:hover{background:rgba(255,255,255,.04);color:var(--text)}
.nav button.active{background:rgba(59,130,246,.18);color:#fff;box-shadow:inset 0 0 0 1px rgba(59,130,246,.35)}
.nav button.hot{color:#93c5fd}
.nav-foot{margin-top:auto;padding:10px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}
.main{display:flex;flex-direction:column;min-width:0;background:radial-gradient(900px 400px at 100% 0%,rgba(59,130,246,.12),transparent 55%),var(--bg)}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 18px;border-bottom:1px solid var(--line);background:rgba(11,18,32,.86)}
.pill{display:inline-flex;align-items:center;gap:8px;padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:rgba(255,255,255,.03);color:var(--muted);font-size:12px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--danger)}.dot.on{background:var(--ok);box-shadow:0 0 0 4px rgba(34,197,94,.18)}
.actions{display:flex;gap:8px;flex-wrap:wrap}
.btn{border:1px solid transparent;border-radius:10px;padding:8px 12px;font-weight:600;font-size:13px;white-space:nowrap}
.btn:active{transform:translateY(1px)}.btn:disabled{opacity:.55;cursor:not-allowed}
.btn-primary{background:linear-gradient(180deg,var(--primary),var(--primary2));color:#fff;box-shadow:0 8px 18px rgba(37,99,235,.28)}
.btn-secondary{background:var(--panel2);border-color:var(--line);color:var(--text)}
.btn-ghost{background:transparent;border-color:var(--line);color:var(--muted)}
.btn-ok{background:rgba(34,197,94,.15);border-color:rgba(34,197,94,.35);color:#86efac}
.btn-sm{padding:6px 10px;font-size:12px}
.content{flex:1;overflow:auto;padding:18px}
.page{display:none}.page.active{display:block}
.head{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;margin-bottom:14px}
.head h2{margin:0;font-size:20px}.head p{margin:4px 0 0;color:var(--muted);font-size:13px}
.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:14px}
.card .k{color:var(--muted);font-size:12px}.card .v{margin-top:8px;font-size:24px;font-weight:700}.card .h{margin-top:6px;color:var(--muted);font-size:12px;min-height:18px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px;margin-bottom:14px}
.panel h3{margin:0 0 4px;font-size:15px}.desc{margin:0 0 14px;color:var(--muted);font-size:12px}
.split{display:grid;grid-template-columns:1.15fr .85fr;gap:14px}
.field{margin-bottom:12px}.field label{display:block;margin-bottom:6px;color:var(--muted);font-size:12px}
.field input,.field textarea,.field select{width:100%;border:1px solid var(--line);background:#0c1424;color:var(--text);border-radius:10px;padding:10px 12px;outline:none}
.field input:focus,.field textarea:focus{border-color:rgba(59,130,246,.55);box-shadow:0 0 0 3px rgba(59,130,246,.15)}
.field textarea{min-height:110px;resize:vertical;font-family:Consolas,monospace;font-size:12px}
.inline{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.inline>input,.inline>code{flex:1;min-width:0}
code.val{display:block;padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:#0c1424;font-family:Consolas,monospace;font-size:12px;overflow:auto;white-space:nowrap}
.steps{display:grid;gap:10px}
.step{display:grid;grid-template-columns:28px 1fr auto;gap:10px;align-items:center;padding:12px;border-radius:12px;border:1px solid var(--line);background:rgba(255,255,255,.02)}
.step .n{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;font-size:12px;font-weight:700;background:rgba(148,163,184,.12);color:var(--muted)}
.step.done .n{background:rgba(34,197,94,.18);color:var(--ok)}
.step .t{font-weight:600;font-size:13px}.step .s{color:var(--muted);font-size:12px}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{border:1px solid var(--line);background:rgba(255,255,255,.03);color:var(--muted);border-radius:999px;padding:6px 10px;font-size:12px}
button.chip{cursor:pointer}.chip.ok{color:var(--ok);border-color:rgba(34,197,94,.35)}.chip.bad{color:#fecaca;border-color:rgba(239,68,68,.35)}.chip.warn{color:#fcd34d;border-color:rgba(245,158,11,.35)}
.hero{border:1px solid rgba(59,130,246,.35);background:linear-gradient(180deg,rgba(59,130,246,.14),rgba(255,255,255,.02));border-radius:var(--radius);padding:16px;margin-bottom:14px}
.hero h3{margin:0 0 4px}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}.grid2 .full{grid-column:1/-1}
a.hl{color:#93c5fd;font-size:12px;text-decoration:none}a.hl:hover{text-decoration:underline}
.toolbar{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
.provider,.route{border:1px solid var(--line);border-radius:12px;background:rgba(255,255,255,.02);margin-bottom:10px;overflow:hidden}
.provider-head{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;padding:12px 14px;cursor:pointer}
.provider-body{display:none;padding:14px;border-top:1px solid var(--line)}.provider.open .provider-body{display:block}
.provider-meta{display:flex;gap:8px;flex-wrap:wrap;margin-top:4px}
.route{padding:12px}.route .name{display:flex;justify-content:space-between;gap:8px;align-items:center}
.dirty{display:none;justify-content:space-between;align-items:center;gap:12px;margin-top:12px;padding:12px 14px;border-radius:12px;border:1px solid rgba(245,158,11,.35);background:rgba(245,158,11,.1)}.dirty.show{display:flex}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:10px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-size:12px}
.empty{padding:24px;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:12px}
.toast{position:fixed;right:18px;bottom:18px;background:#0f2744;border:1px solid rgba(59,130,246,.4);color:var(--text);padding:10px 14px;border-radius:10px;opacity:0;transform:translateY(8px);pointer-events:none;transition:.2s;z-index:80;max-width:380px}
.toast.show{opacity:1;transform:none}.toast.err{border-color:rgba(239,68,68,.45);background:#3a1520}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:90;padding:20px}
.modal.show{display:flex}.modal-card{width:min(460px,100%);background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 20px 50px rgba(0,0,0,.45)}
.probe-list{display:grid;gap:8px}.probe-item{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.02)}
@media(max-width:980px){.cards,.grid2,.split{grid-template-columns:1fr}:root{--nav:168px}}
</style>
</head>
<body>
<div class="app">
<aside class="nav">
  <div class="brand"><div class="logo">帅</div><div><h1>大帅网关</h1><p>本地模型网关</p></div></div>
  <button type="button" class="active" data-page="home">首页</button>
  <button type="button" class="hot" data-page="setup">一键配置</button>
  <button type="button" data-page="connect">一键接入</button>
  <button type="button" data-page="providers">上游渠道</button>
  <button type="button" data-page="routes">路由模型</button>
  <button type="button" data-page="monitor">运行监控</button>
  <div class="nav-foot"><div id="navVer">v—</div><div style="margin-top:4px">可最小化到托盘</div></div>
</aside>
<section class="main">
<header class="top">
  <div class="pill"><span class="dot" id="liveDot"></span><span id="liveText">检测中…</span></div>
  <div class="actions">
    <button class="btn btn-ghost btn-sm" type="button" id="btnRefresh">刷新</button>
    <button class="btn btn-secondary btn-sm" type="button" id="btnSyncWb">同步 WorkBuddy</button>
    <button class="btn btn-primary btn-sm" type="button" id="btnCopyAll">复制接入信息</button>
  </div>
</header>
<div class="content">

<div class="page active" id="page-home">
  <div class="head"><div><h2>先做这两步</h2><p>导入 Key → 同步/复制给客户端</p></div></div>
  <div class="hero">
    <h3>一键配置（推荐）</h3>
    <p class="desc">只填 3 个上游 Key，点一次导入。导入后可一键同步到 WorkBuddy。</p>
    <div class="inline">
      <button class="btn btn-primary" type="button" data-go="setup">去填 3 个 Key</button>
      <button class="btn btn-secondary" type="button" data-go="connect">去一键接入</button>
    </div>
  </div>
  <div class="cards">
    <div class="card"><div class="k">网关</div><div class="v" id="statOnline">—</div><div class="h" id="statOnlineHint">本机服务</div></div>
    <div class="card"><div class="k">可用渠道</div><div class="v" id="statReady">—</div><div class="h" id="statReadyHint">已填有效 Key</div></div>
    <div class="card"><div class="k">路由模型</div><div class="v" id="statRoutes">—</div><div class="h">daily / fast…</div></div>
    <div class="card"><div class="k">累计调用</div><div class="v" id="statCalls">—</div><div class="h" id="statCallsHint">最近记录</div></div>
  </div>
  <div class="split">
    <div class="panel"><h3>清单</h3><p class="desc">按顺序完成即可。</p><div class="steps" id="homeSteps"></div></div>
    <div class="panel">
      <h3>最常复制</h3><p class="desc">客户端一般只要这两项 + 模型名 daily。</p>
      <div class="field"><label>OpenAI Base URL</label><div class="inline"><code class="val" id="homeBase">http://127.0.0.1:8010/v1</code><button class="btn btn-secondary btn-sm" type="button" data-copy="#homeBase">复制</button></div></div>
      <div class="field"><label>本地 API Key</label><div class="inline"><code class="val" id="homeKey">sk-local-change-me</code><button class="btn btn-secondary btn-sm" type="button" data-copy="#homeKey">复制</button></div></div>
      <div class="field"><label>推荐模型</label><div class="chips" id="homeRoutes"></div></div>
    </div>
  </div>
</div>

<div class="page" id="page-setup">
  <div class="head"><div><h2>一键配置</h2><p>填 Key → 导入启用 → 探测 → 同步 WorkBuddy</p></div></div>
  <div class="hero">
    <h3>三 Key 导入</h3>
    <p class="desc">留空会跳过。导入成功后会自动探测，并把结果列在下方。</p>
    <div class="grid2">
      <div class="field"><label>1. NVIDIA Key <a class="hl" href="https://build.nvidia.com/" target="_blank" rel="noreferrer">去申请</a></label><div class="inline"><input id="setupNvidia" type="password" placeholder="nvapi-..." autocomplete="off" /><button class="btn btn-ghost btn-sm" type="button" data-toggle="#setupNvidia">显示</button></div></div>
      <div class="field"><label>2. 魔搭 ModelScope Key <a class="hl" href="https://modelscope.cn/my/myaccesstoken" target="_blank" rel="noreferrer">去申请</a></label><div class="inline"><input id="setupMs" type="password" placeholder="ms-..." autocomplete="off" /><button class="btn btn-ghost btn-sm" type="button" data-toggle="#setupMs">显示</button></div></div>
      <div class="field"><label>3. OpenAI 兼容 Key（可选）</label><div class="inline"><input id="setupOai" type="password" placeholder="sk-..." autocomplete="off" /><button class="btn btn-ghost btn-sm" type="button" data-toggle="#setupOai">显示</button></div></div>
      <div class="field"><label>3. Base URL（可选）</label><input id="setupOaiBase" type="text" placeholder="https://api.openai.com/v1" autocomplete="off" /></div>
      <div class="field full"><label>或整段粘贴（自动识别）</label><textarea id="setupPaste" placeholder="把 Key 随便贴进来，一行一个也行"></textarea></div>
    </div>
    <div class="inline">
      <button class="btn btn-primary" type="button" id="btnImportKeys">一键导入并启用</button>
      <button class="btn btn-ok" type="button" id="btnImportSync">导入 + 同步 WorkBuddy</button>
      <button class="btn btn-secondary" type="button" id="btnParsePaste">从粘贴区识别</button>
      <button class="btn btn-ghost" type="button" id="btnClearSetup">清空</button>
      <span class="chip" id="setupResult">等待导入</span>
    </div>
  </div>
  <div class="panel">
    <h3>探测结果</h3>
    <p class="desc">导入后自动探测；也可稍后在上游渠道里单独探测。</p>
    <div id="probeBox" class="empty">还没有探测结果</div>
  </div>
</div>

<div class="page" id="page-connect">
  <div class="head"><div><h2>一键接入</h2><p>复制给客户端，或直接同步 WorkBuddy</p></div></div>
  <div class="split">
    <div class="panel">
      <h3>连接参数</h3><p class="desc">本地 Key 必须和客户端 API Key 一致。</p>
      <div class="field"><label>OpenAI Base URL</label><div class="inline"><code class="val" id="connBase">http://127.0.0.1:8010/v1</code><button class="btn btn-secondary btn-sm" type="button" data-copy="#connBase">复制</button></div></div>
      <div class="field"><label>本地 API Key</label><div class="inline"><input id="localKey" type="password" autocomplete="off" /><button class="btn btn-ghost btn-sm" type="button" id="btnToggleKey">显示</button><button class="btn btn-primary btn-sm" type="button" id="btnSaveKey">保存</button></div></div>
      <div class="field"><label>当前掩码</label><span class="chip" id="keyMasked">—</span></div>
      <div class="field"><label>路由模型</label><div class="chips" id="connRoutes"></div></div>
      <div class="inline">
        <button class="btn btn-ok" type="button" id="btnSyncWb2">同步到 WorkBuddy</button>
        <button class="btn btn-secondary" type="button" id="btnCopyCursor">复制 Cursor 片段</button>
      </div>
    </div>
    <div class="panel">
      <h3>配置片段</h3><p class="desc">WorkBuddy / 自定义 OpenAI 兼容客户端。</p>
      <textarea id="wbSnippet" readonly></textarea>
      <div class="inline" style="margin-top:10px">
        <button class="btn btn-primary" type="button" id="btnCopyWb">复制片段</button>
        <button class="btn btn-secondary" type="button" id="btnCopyCurl">复制 curl</button>
      </div>
    </div>
  </div>
</div>

<div class="page" id="page-providers">
  <div class="head"><div><h2>上游渠道</h2><p>可细调；日常用「一键配置」即可</p></div></div>
  <div class="panel">
    <div class="toolbar"><span class="chip" id="provSummary">—</span><div class="inline"><button class="btn btn-secondary btn-sm" type="button" id="btnAddProvider">新增</button><button class="btn btn-primary btn-sm" type="button" id="btnSaveProviders">保存全部</button></div></div>
    <div id="providers"></div>
    <div class="dirty" id="provDirty"><span>有未保存修改</span><button class="btn btn-primary btn-sm" type="button" id="btnSaveProviders2">立即保存</button></div>
  </div>
</div>

<div class="page" id="page-routes">
  <div class="head"><div><h2>路由模型</h2><p>客户端 model 填路由名</p></div><button class="btn btn-primary btn-sm" type="button" id="btnSaveRoutes">保存路由</button></div>
  <div class="panel"><div id="routesBox"></div><button class="btn btn-secondary btn-sm" type="button" id="btnAddRoute" style="margin-top:8px">新增路由</button></div>
</div>

<div class="page" id="page-monitor">
  <div class="head"><div><h2>运行监控</h2><p>渠道健康与用量</p></div></div>
  <div class="split">
    <div class="panel"><h3>渠道健康</h3><p class="desc">分数越高越优先。</p><div style="overflow:auto"><table><thead><tr><th>渠道</th><th>模型</th><th>分数</th><th>延迟</th><th>状态</th></tr></thead><tbody id="channels"><tr><td colspan="5" style="color:var(--muted)">暂无数据</td></tr></tbody></table></div></div>
    <div class="panel"><h3>用量</h3><p class="desc">本地调用记录。</p><div id="usageBox" class="empty">暂无用量</div></div>
  </div>
</div>

</div>
</section>
</div>

<div class="modal" id="keyModal">
  <div class="modal-card">
    <h3 style="margin:0 0 6px">建议修改本地 API Key</h3>
    <p class="desc">当前还是默认 Key，任何人都能调用你的网关。改一个自己的更安全。</p>
    <div class="field"><label>新的本地 API Key</label><input id="modalKey" type="text" placeholder="例如 sk-dashuai-你的密码" /></div>
    <div class="inline">
      <button class="btn btn-primary" type="button" id="btnModalSave">保存并继续</button>
      <button class="btn btn-ghost" type="button" id="btnModalSkip">稍后</button>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>
<script>
const PRESETS = {
  NVIDIA: {name:"NVIDIA", base_url:"https://integrate.api.nvidia.com/v1", models:["meta/llama-3.1-8b-instruct","nvidia/llama-3.1-nemotron-70b-instruct"], free_only:true, weight:10, enabled:true},
  ModelScope: {name:"ModelScope", base_url:"https://api-inference.modelscope.cn/v1", models:["Qwen/Qwen2.5-72B-Instruct"], free_only:true, weight:8, enabled:true},
  "OpenAI-Compatible": {name:"OpenAI-Compatible", base_url:"https://api.openai.com/v1", models:["gpt-4o-mini"], free_only:false, weight:5, enabled:true},
};
const state = {
  overview: null,
  providers: [],
  routes: {},
  localKey: localStorage.getItem("dashuai_local_key") || "sk-local-change-me",
  dirty: false,
  open: 0,
  lastProbes: [],
};
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

function toast(msg, err=false){
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("err", !!err);
  el.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("show"), 2600);
}
function auth(){ return { Authorization: `Bearer ${state.localKey}`, "Content-Type": "application/json" }; }
async function copyText(t){ t=String(t||"").trim(); if(!t) return; await navigator.clipboard.writeText(t); toast("已复制"); }
function go(page){
  $$(".nav button[data-page]").forEach(b => b.classList.toggle("active", b.dataset.page === page));
  $$(".page").forEach(p => p.classList.toggle("active", p.id === `page-${page}`));
}
function esc(s){ return String(s??"").replaceAll("&","&amp;").replaceAll('"',"&quot;").replaceAll("<","&lt;"); }
function keyOk(k){
  const s = String(k||"").trim();
  if (!s) return false;
  if (s.startsWith("REPLACE_") || s.includes("YOUR_KEY") || s.includes("change-me") || s.includes("example.com")) return false;
  return true;
}
function norm(p){
  return {
    name: p.name || "unnamed",
    base_url: p.base_url || "",
    api_key: p.api_key || "",
    models: Array.isArray(p.models) ? p.models : [],
    free_only: !!(p.free_only),
    weight: Number(p.weight ?? 1),
    enabled: p.enabled !== false,
  };
}
function wbSnippet(base, key){
  return JSON.stringify({
    id: "daily", name: "大帅网关 · daily", vendor: "Custom", url: base, apiKey: key,
    supportsToolCall: true, supportsImages: true, supportsReasoning: true,
    maxInputTokens: 1048576, maxOutputTokens: 32768
  }, null, 2);
}
function curlSnippet(base, key){
  return `curl ${base}/chat/completions \\\n  -H "Authorization: Bearer ${key}" \\\n  -H "Content-Type: application/json" \\\n  -d "{\\"model\\":\\"daily\\",\\"messages\\":[{\\"role\\":\\"user\\",\\"content\\":\\"你好\\"}]}"`;
}
function cursorSnippet(base, key){
  return JSON.stringify({
    "dashuai-gateway": {
      "name": "大帅网关",
      "baseUrl": base,
      "apiKey": key,
      "models": Object.keys(state.routes || {daily:1, fast:1})
    }
  }, null, 2);
}
function chips(sel, routes){
  const el = $(sel); const names = Object.keys(routes||{});
  if (!names.length){ el.innerHTML = `<span class="chip">暂无路由</span>`; return; }
  el.innerHTML = names.map(n => `<button class="chip" type="button" data-ct="${esc(n)}">${esc(n)}</button>`).join("");
  el.querySelectorAll("[data-ct]").forEach(b => b.onclick = () => copyText(b.dataset.ct));
}
function findIdx(list, name){
  const n = String(name||"").toLowerCase();
  return list.findIndex(p => {
    const pn = String(p.name||"").toLowerCase();
    return pn === n || pn.includes(n) || n.includes(pn);
  });
}
function upsert(list, presetName, apiKey, baseUrl){
  const key = String(apiKey||"").trim();
  const base = String(baseUrl||"").trim();
  if (!keyOk(key) && !base) return false;
  const preset = PRESETS[presetName];
  let i = findIdx(list, presetName);
  if (i < 0){
    list.push(norm({...preset, api_key: key||"", base_url: base||preset.base_url, enabled: keyOk(key)}));
    return true;
  }
  if (keyOk(key)){ list[i].api_key = key; list[i].enabled = true; }
  if (base) list[i].base_url = base;
  if (!list[i].models?.length) list[i].models = preset.models.slice();
  return true;
}
function renderProbe(results){
  const box = $("#probeBox");
  if (!results?.length){ box.className="empty"; box.textContent="还没有探测结果"; return; }
  box.className="probe-list";
  box.innerHTML = results.map(r => `
    <div class="probe-item">
      <div><strong>${esc(r.name)}</strong><div class="desc" style="margin:4px 0 0">${esc(r.detail||"")}</div></div>
      <span class="chip ${r.ok?"ok":"bad"}">${r.ok ? ("成功 " + (r.ms||0) + "ms") : "失败"}</span>
    </div>`).join("");
}
function renderHome(j){
  const ready = j.providers_ready || [];
  const routes = j.routes || {};
  const usage = j.usage || {};
  const online = !!j.ok;
  const base = j.openai_base || "http://127.0.0.1:8010/v1";
  $("#liveDot").classList.toggle("on", online);
  $("#liveText").textContent = online ? `在线 · ${ready.length} 个可用渠道 · :${j.config?.port || 8010}` : "离线";
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
  chips("#homeRoutes", routes); chips("#connRoutes", routes);
  $("#wbSnippet").value = wbSnippet(base, state.localKey);
  const weak = !keyOk(state.localKey) || state.localKey === "sk-local-change-me";
  const steps = [
    {done: ready.length>0, title:"导入上游 Key", tip:"打开「一键配置」填 3 个 Key", action:"去配置", page:"setup"},
    {done: !weak, title:"修改默认本地 Key", tip:"默认 Key 不安全，建议改掉", action:"去接入", page:"connect"},
    {done: Object.keys(routes).length>0, title:"选用模型名", tip:"客户端 model 填 daily / fast", action:"看路由", page:"routes"},
    {done: (usage.total??0)>0, title:"发一次测试 / 同步 WorkBuddy", tip:"点顶部「同步 WorkBuddy」后重启客户端", action:"去接入", page:"connect"},
  ];
  $("#homeSteps").innerHTML = steps.map((s,i)=>`
    <div class="step ${s.done?"done":""}"><div class="n">${s.done?"✓":(i+1)}</div>
    <div><div class="t">${s.title}</div><div class="s">${s.tip}</div></div>
    <button class="btn btn-secondary btn-sm" type="button" data-go="${s.page}">${s.action}</button></div>`).join("");
}
function renderMonitor(j){
  const channels = j.channels || [];
  $("#channels").innerHTML = channels.length ? channels.map(c => `
    <tr><td>${esc(c.provider)}</td><td>${esc(c.model)}</td><td>${c.score??"—"}</td>
    <td>${c.last_latency_ms!=null?c.last_latency_ms+" ms":"—"}</td>
    <td>${c.circuit_open?'<span class="chip bad">熔断</span>':'<span class="chip ok">可用</span>'}</td></tr>`).join("") :
    `<tr><td colspan="5" style="color:var(--muted)">尚无调用记录</td></tr>`;
  const by = (j.usage||{}).by_provider || {};
  const names = Object.keys(by);
  if (!names.length){ $("#usageBox").className="empty"; $("#usageBox").textContent="暂无用量"; }
  else {
    $("#usageBox").className="";
    $("#usageBox").innerHTML = names.map(n => {
      const s = by[n];
      return `<div class="step done" style="margin-bottom:8px"><div class="n">●</div><div><div class="t">${esc(n)}</div><div class="s">调用 ${s.calls??0} · 成功 ${s.ok??0}</div></div><span></span></div>`;
    }).join("");
  }
}
function renderProviders(){
  const list = state.providers;
  const ready = list.filter(p => p.enabled && keyOk(p.api_key) && p.models.length).length;
  $("#provSummary").textContent = `${list.length} 个渠道 · ${ready} 个可用`;
  $("#provDirty").classList.toggle("show", state.dirty);
  const box = $("#providers");
  if (!list.length){ box.innerHTML = `<div class="empty">还没有渠道</div>`; return; }
  box.innerHTML = list.map((p,i) => {
    const ok = p.enabled && keyOk(p.api_key) && (p.models||[]).length>0;
    return `<div class="provider ${state.open===i?"open":""}">
      <div class="provider-head" data-toggle="${i}"><div><strong>${esc(p.name||"未命名")}</strong>
        <div class="provider-meta"><span class="chip ${ok?"ok":"bad"}">${ok?"可用":"待配置"}</span>
        <span class="chip">${p.enabled?"已启用":"已关闭"}</span></div></div>
        <div class="inline" onclick="event.stopPropagation()">
          <label class="switch"><input type="checkbox" data-f="enabled" data-i="${i}" ${p.enabled?"checked":""}/>启用</label>
          <button class="btn btn-ghost btn-sm" type="button" data-probe="${i}">探测</button>
        </div></div>
      <div class="provider-body">
        <div class="field"><label>名称</label><input data-f="name" data-i="${i}" value="${esc(p.name)}" /></div>
        <div class="field"><label>Base URL</label><input data-f="base_url" data-i="${i}" value="${esc(p.base_url)}" /></div>
        <div class="field"><label>API Key</label><input data-f="api_key" data-i="${i}" type="password" value="${esc(p.api_key)}" /></div>
        <div class="field"><label>模型（逗号分隔）</label><input data-f="models" data-i="${i}" value="${esc((p.models||[]).join(", "))}" /></div>
        <div class="inline">
          <div class="field" style="flex:1;margin:0"><label>权重</label><input data-f="weight" data-i="${i}" type="number" value="${p.weight??1}" /></div>
          <button class="btn btn-danger btn-sm" type="button" data-del="${i}" style="margin-top:18px">删除</button>
        </div>
        <div class="chip" data-pr="${i}">未探测</div>
      </div></div>`;
  }).join("");
  box.querySelectorAll("[data-toggle]").forEach(el => el.onclick = () => { const i=+el.dataset.toggle; state.open = state.open===i?-1:i; renderProviders(); });
  box.querySelectorAll("[data-f]").forEach(el => {
    el.oninput = el.onchange = () => {
      const p = state.providers[+el.dataset.i]; if (!p) return;
      const f = el.dataset.f;
      if (f === "enabled") p.enabled = el.checked;
      else if (f === "weight") p.weight = Number(el.value||1);
      else if (f === "models") p.models = el.value.split(",").map(s=>s.trim()).filter(Boolean);
      else p[f] = el.value;
      state.dirty = true; $("#provDirty").classList.add("show");
    };
  });
  box.querySelectorAll("[data-probe]").forEach(b => b.onclick = e => { e.stopPropagation(); probeOne(+b.dataset.probe); });
  box.querySelectorAll("[data-del]").forEach(b => b.onclick = e => { e.stopPropagation(); state.providers.splice(+b.dataset.del,1); state.dirty=true; renderProviders(); });
}
function renderRoutes(){
  const box = $("#routesBox"); const entries = Object.entries(state.routes||{});
  if (!entries.length){ box.innerHTML = `<div class="empty">暂无路由</div>`; return; }
  box.innerHTML = entries.map(([id,m]) => `
    <div class="route" data-rid="${esc(id)}"><div class="name"><strong>${esc(id)}</strong>
    <button class="btn btn-ghost btn-sm" type="button" data-delr="${esc(id)}">删除</button></div>
    <div class="field" style="margin-top:10px"><label>说明</label><input data-rf="description" value="${esc((m||{}).description||"")}" /></div>
    <div class="field"><label>候选模型</label><input data-rf="candidates" value="${esc(((m||{}).candidates||[]).join(", "))}" /></div></div>`).join("");
  box.querySelectorAll("[data-delr]").forEach(b => b.onclick = () => { delete state.routes[b.dataset.delr]; renderRoutes(); });
}
function collectRoutes(){
  const next = {};
  $$("#routesBox .route").forEach(card => {
    next[card.dataset.rid] = {
      description: card.querySelector('[data-rf="description"]').value.trim(),
      candidates: card.querySelector('[data-rf="candidates"]').value.split(",").map(s=>s.trim()).filter(Boolean),
    };
  });
  state.routes = next; return next;
}
async function saveProviders(show=true){
  const r = await fetch("/api/providers", { method:"PUT", headers:auth(), body: JSON.stringify(state.providers.map(norm)) });
  if (!r.ok) throw new Error(await r.text());
  state.dirty = false; $("#provDirty").classList.remove("show");
  if (show) toast("渠道已保存");
  await refresh();
}
async function probeOne(i){
  const p = state.providers[i]; if (!p) return;
  const chip = document.querySelector(`[data-pr="${i}"]`);
  if (chip) chip.textContent = "探测中…";
  try{
    await saveProviders(false);
    const r = await fetch("/api/probe", { method:"POST", headers:auth(), body: JSON.stringify({name:p.name}) });
    const j = await r.json().catch(()=>({}));
    if (!r.ok) throw 0;
    const ok = !!j.ok; const ms = j.latency_ms || j.latency || 0;
    if (chip) chip.textContent = ok ? `成功 ${ms}ms` : "失败";
    toast(ok ? `${p.name} 探测成功` : `${p.name} 探测失败`, !ok);
    refresh();
  }catch{ if (chip) chip.textContent="失败"; toast("探测失败", true); }
}
function parsePaste(){
  const raw = ($("#setupPaste").value||"").trim();
  if (!raw){ toast("粘贴区是空的", true); return; }
  const tokens = raw.split(/[\s,;|]+/).map(s=>s.trim()).filter(s=>s.length>=8);
  let nvidia="", ms="", oai="";
  for (const t of tokens){
    const low = t.toLowerCase();
    if (!nvidia && (low.startsWith("nvapi-") || low.includes("nvapi"))) nvidia = t;
    else if (!ms && (low.startsWith("ms-") || low.includes("modelscope"))) ms = t;
    else if (!oai && (low.startsWith("sk-") || low.startsWith("sk_"))) oai = t;
  }
  const rest = tokens.filter(t => t!==nvidia && t!==ms && t!==oai);
  if (!nvidia && rest.length) nvidia = rest.shift();
  if (!ms && rest.length) ms = rest.shift();
  if (!oai && rest.length) oai = rest.shift();
  if (nvidia) $("#setupNvidia").value = nvidia;
  if (ms) $("#setupMs").value = ms;
  if (oai) $("#setupOai").value = oai;
  const n = [nvidia,ms,oai].filter(Boolean).length;
  $("#setupResult").textContent = n ? `已识别 ${n} 个 Key` : "未识别到 Key";
  toast(n ? `已识别 ${n} 个 Key` : "未识别到 Key", !n);
}
async function importKeys(){
  const nvidia = $("#setupNvidia").value.trim();
  const ms = $("#setupMs").value.trim();
  const oai = $("#setupOai").value.trim();
  const oaiBase = $("#setupOaiBase").value.trim();
  if (!keyOk(nvidia) && !keyOk(ms) && !keyOk(oai) && !oaiBase){
    toast("请至少填 1 个有效 Key", true); return false;
  }
  $("#setupResult").textContent = "导入中…";
  $("#btnImportKeys").disabled = true;
  $("#btnImportSync").disabled = true;
  try{
    const pr = await fetch("/api/providers", { headers: auth() });
    if (!pr.ok) throw new Error("auth " + pr.status);
    state.providers = ((await pr.json())||[]).map(norm);
    const list = state.providers.slice();
    let n = 0;
    if (upsert(list, "NVIDIA", nvidia)) n++;
    if (upsert(list, "ModelScope", ms)) n++;
    if (upsert(list, "OpenAI-Compatible", oai, oaiBase)) n++;
    state.providers = list;
    await saveProviders(false);
    $("#setupResult").textContent = `已导入 ${n} 项`;
    toast(`导入成功（${n} 项）`);
    // probe
    const results = [];
    for (const p of state.providers){
      if (!(p.enabled && keyOk(p.api_key))) continue;
      try{
        const r = await fetch("/api/probe", { method:"POST", headers:auth(), body: JSON.stringify({name:p.name}) });
        const j = await r.json().catch(()=>({}));
        results.push({ name:p.name, ok:!!j.ok, ms:j.latency_ms||j.latency||0, detail: j.ok ? "连通正常" : (j.detail || j.error || "探测失败") });
      }catch(e){
        results.push({ name:p.name, ok:false, ms:0, detail: String(e.message||e) });
      }
    }
    state.lastProbes = results;
    renderProbe(results);
    await refresh();
    return true;
  }catch(e){
    $("#setupResult").textContent = "导入失败";
    toast("导入失败：本地 API Key 不正确，或服务未就绪", true);
    console.error(e);
    return false;
  }finally{
    $("#btnImportKeys").disabled = false;
    $("#btnImportSync").disabled = false;
  }
}
async function syncWorkBuddy(){
  try{
    const r = await fetch("/api/integrations/workbuddy", { method:"POST", headers:auth() });
    const j = await r.json().catch(()=>({}));
    if (!r.ok) throw new Error(j.detail || "sync failed");
    toast(`已同步 WorkBuddy：${j.path || ""}`);
    return true;
  }catch(e){
    toast("同步失败：" + (e.message||"未知错误"), true);
    return false;
  }
}
async function refresh(){
  try{
    const r = await fetch("/api/overview");
    if (!r.ok) throw 0;
    const j = await r.json();
    state.overview = j; state.routes = j.routes || {};
    renderHome(j); renderMonitor(j); renderRoutes();
    if (j.port_warning) toast(j.port_warning, true);
  }catch{
    $("#liveDot").classList.remove("on");
    $("#liveText").textContent = "无法连接网关";
    toast("网关未响应", true);
  }
  try{
    const r = await fetch("/api/providers", { headers: auth() });
    if (r.ok){ state.providers = ((await r.json())||[]).map(norm); renderProviders(); }
  }catch{}
}
function maybeAskLocalKey(){
  if (localStorage.getItem("dashuai_key_prompted")) return;
  if (state.localKey !== "sk-local-change-me") return;
  $("#modalKey").value = "sk-dashuai-" + Math.random().toString(36).slice(2,10);
  $("#keyModal").classList.add("show");
}

$$(".nav button[data-page]").forEach(b => b.onclick = () => go(b.dataset.page));
document.body.addEventListener("click", (e) => {
  const goBtn = e.target.closest("[data-go]"); if (goBtn) go(goBtn.dataset.go);
  const c = e.target.closest("[data-copy]"); if (c){ const el=document.querySelector(c.dataset.copy); copyText(el?.textContent||el?.value||""); }
  const t = e.target.closest("[data-toggle]"); if (t){ const input=document.querySelector(t.dataset.toggle); if(!input) return; input.type = input.type==="password"?"text":"password"; t.textContent = input.type==="password"?"显示":"隐藏"; }
});
$("#btnRefresh").onclick = refresh;
$("#btnCopyAll").onclick = () => {
  const base = state.overview?.openai_base || $("#homeBase").textContent;
  copyText(`Base URL: ${base}\nAPI Key: ${state.localKey}\nModel: daily`);
};
$("#btnCopyWb").onclick = () => copyText($("#wbSnippet").value);
$("#btnCopyCurl").onclick = () => copyText(curlSnippet(state.overview?.openai_base || $("#connBase").textContent, state.localKey));
$("#btnCopyCursor").onclick = () => copyText(cursorSnippet(state.overview?.openai_base || $("#connBase").textContent, state.localKey));
$("#btnSyncWb").onclick = syncWorkBuddy;
$("#btnSyncWb2").onclick = syncWorkBuddy;
$("#localKey").value = state.localKey;
$("#btnToggleKey").onclick = () => { const el=$("#localKey"); el.type = el.type==="password"?"text":"password"; $("#btnToggleKey").textContent = el.type==="password"?"显示":"隐藏"; };
$("#btnSaveKey").onclick = async () => {
  const newKey = $("#localKey").value.trim();
  if (!newKey) return toast("Key 不能为空", true);
  try{
    const curResp = await fetch("/api/config", { headers: auth() });
    if (!curResp.ok) throw 0;
    const cur = await curResp.json();
    cur.local_api_key = newKey;
    const r = await fetch("/api/config", { method:"PUT", headers:auth(), body: JSON.stringify(cur) });
    if (!r.ok) throw 0;
    state.localKey = newKey;
    localStorage.setItem("dashuai_local_key", newKey);
    $("#homeKey").textContent = newKey;
    toast("本地 Key 已保存");
    refresh();
  }catch{ toast("保存失败：当前本地 Key 不正确", true); }
};
$("#btnModalSave").onclick = async () => {
  const newKey = $("#modalKey").value.trim();
  if (!newKey) return toast("请填写新 Key", true);
  $("#localKey").value = newKey;
  localStorage.setItem("dashuai_key_prompted", "1");
  $("#keyModal").classList.remove("show");
  await $("#btnSaveKey").onclick();
};
$("#btnModalSkip").onclick = () => { localStorage.setItem("dashuai_key_prompted","1"); $("#keyModal").classList.remove("show"); };
$("#btnImportKeys").onclick = async () => { if (await importKeys()) go("connect"); };
$("#btnImportSync").onclick = async () => {
  if (await importKeys()){ await syncWorkBuddy(); go("connect"); }
};
$("#btnParsePaste").onclick = parsePaste;
$("#btnClearSetup").onclick = () => {
  ["setupNvidia","setupMs","setupOai","setupOaiBase","setupPaste"].forEach(id => { const el=document.getElementById(id); if(el) el.value=""; });
  $("#setupResult").textContent = "已清空";
};
$("#btnAddProvider").onclick = () => {
  state.providers.push(norm({...PRESETS["OpenAI-Compatible"], name:`渠道-${state.providers.length+1}`, api_key:"", enabled:true}));
  state.open = state.providers.length-1; state.dirty=true; renderProviders();
};
const saveProv = async () => { try{ await saveProviders(true);} catch{ toast("保存失败：检查本地 API Key", true);} };
$("#btnSaveProviders").onclick = saveProv; $("#btnSaveProviders2").onclick = saveProv;
$("#btnAddRoute").onclick = () => {
  collectRoutes(); let i=1, id=`route-${i}`; while(state.routes[id]){i++; id=`route-${i}`;}
  state.routes[id] = {description:"新路由", candidates:[]}; renderRoutes();
};
$("#btnSaveRoutes").onclick = async () => {
  try{
    const body = collectRoutes();
    const r = await fetch("/api/routers", { method:"PUT", headers:auth(), body: JSON.stringify(body) });
    if (!r.ok) throw 0; toast("路由已保存"); refresh();
  }catch{ toast("保存路由失败", true); }
};

refresh().then(() => {
  maybeAskLocalKey();
  const ready = state.overview?.providers_ready || [];
  if (!ready.length && !sessionStorage.getItem("dashuai_setup_seen")) {
    sessionStorage.setItem("dashuai_setup_seen","1");
    go("setup");
    toast("先填 3 个 Key，再点「一键导入并启用」");
  }
});
setInterval(refresh, 15000);
</script>
</body>
</html>
'''

OUT.write_text(HTML, encoding="utf-8")
print("wrote", OUT, "bytes", OUT.stat().st_size)
