# -*- coding: utf-8 -*-
"""Surgical fix: restore broken go(), wire setup buttons, add probe panel hooks."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "web" / "index.html"

text = HTML.read_text(encoding="utf-8")

# --- 1) Fix corrupted go() that swallowed PRESETS/import ---
# Pattern: function go(page){ <PRESETS...clearSetup...> $$(".nav...page...") }
old = re.search(
    r"function go\(page\)\{\s*const PRESETS = \{.*?"
    r"function clearSetupForm\(\) \{.*?\n\}\s*\n\s*"
    r'(\$\$\("\.nav button\[data-page\]"\)\.forEach\(b => b\.classList\.toggle\("active", b\.dataset\.page === page\)\);\s*'
    r'\$\$\("\.page"\)\.forEach\(p => p\.classList\.toggle\("active", p\.id === `page-\$\{page\}`\)\);\s*\})',
    text,
    flags=re.S,
)
if not old:
    # try alternate from earlier corruption shape
    old = re.search(
        r"function go\(page\)\{\s*\nconst PRESETS = \{.*?"
        r"function clearSetupForm\(\)[\s\S]*?\n\}\s*\n\s*"
        r'(\$\$\("\.nav button\[data-page\]"\)[\s\S]*?p\.id === `page-\$\{page\}`\)\);\s*\n\})',
        text,
        flags=re.S,
    )

if old:
    block = old.group(0)
    # extract helpers: from const PRESETS to end of clearSetupForm
    m = re.search(
        r"(const PRESETS = \{.*?\nfunction clearSetupForm\(\)[\s\S]*?\n\})\s*\n\s*"
        r"(\$\$\(\"\.nav button\[data-page\]\"\)[\s\S]*?p\.id === `page-\$\{page\}`\)\);\s*\n\})",
        block,
        flags=re.S,
    )
    if not m:
        raise SystemExit("could not split go() internals")
    helpers = m.group(1)
    go_body = m.group(2)
    replacement = (
        helpers
        + "\n\nfunction go(page){\n  "
        + go_body.replace("$$(\".nav button[data-page]\")", "$$(\".nav button[data-page]\")", 1)
    )
    # go_body already includes the forEach lines and closing }; make proper go
    replacement = helpers + "\n\nfunction go(page){\n  " + go_body.lstrip()
    text = text[: old.start()] + replacement + text[old.end() :]
    print("fixed go()")
else:
    # Already fixed?
    if "function go(page){\n  $$(\".nav button[data-page]\")" in text or 'function go(page){\n  $$(".nav button[data-page]")' in text:
        print("go() already looks ok")
    else:
        # dump snippet for debug
        i = text.find("function go(page)")
        print("go() pattern not found, snippet:")
        print(repr(text[i : i + 200]))
        raise SystemExit(1)

# --- 2) CSS extras ---
if ".probe-list{" not in text:
    text = text.replace(
        "@media (max-width:980px)",
        """.chip.warn{color:#fcd34d;border-color:rgba(245,158,11,.35)}
.btn-ok{background:rgba(34,197,94,.16);border-color:rgba(34,197,94,.35);color:#86efac}
.probe-list{display:grid;gap:8px}
.probe-item{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.02)}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:90;padding:20px}
.modal.show{display:flex}
.modal-card{width:min(460px,100%);background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 20px 50px rgba(0,0,0,.45)}
.modal-card h3{margin:0 0 6px}
@media (max-width:980px)""",
        1,
    )

# --- 3) HTML: sync buttons + probe + modal ---
if 'id="btnSyncWbTop"' not in text:
    text = text.replace(
        '<button class="btn btn-ghost btn-sm" type="button" id="btnRefresh">刷新</button>',
        '<button class="btn btn-ghost btn-sm" type="button" id="btnRefresh">刷新</button>\n'
        '        <button class="btn btn-secondary btn-sm" type="button" id="btnSyncWbTop">同步 WorkBuddy</button>',
        1,
    )

text = text.replace("关掉窗口即退出", "可最小化到托盘")

if 'id="btnImportSync"' not in text:
    text = text.replace(
        '<button class="btn btn-primary" type="button" id="btnImportKeys">一键导入并启用</button>',
        '<button class="btn btn-primary" type="button" id="btnImportKeys">一键导入并启用</button>\n'
        '            <button class="btn btn-ok" type="button" id="btnImportSync">导入并同步 WorkBuddy</button>',
        1,
    )

if 'id="probeBox"' not in text:
    text = text.replace(
        """        <div class="panel">
          <h3>导入后做什么？</h3>
          <p class="desc">导入成功后，去「一键接入」复制 Base URL + 本地 Key 给客户端；模型名填 daily / fast。</p>
          <div class="inline">
            <button class="btn btn-secondary" type="button" data-go="connect">去一键接入</button>
            <button class="btn btn-ghost" type="button" data-go="providers">查看上游渠道</button>
          </div>
        </div>
      </div>

      <div class="page" id="page-connect">""",
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
      </div>

      <div class="page" id="page-connect">""",
        1,
    )

if 'id="btnSyncWb2"' not in text:
    text = text.replace(
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
          </div>
        </div>
      </div>

      <div class="page" id="page-providers">""",
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
          </div>
        </div>
      </div>

      <div class="page" id="page-providers">""",
        1,
    )

if 'id="keyModal"' not in text:
    text = text.replace(
        '<div class="toast" id="toast"></div>',
        """<div class="modal" id="keyModal">
  <div class="modal-card">
    <h3>建议修改本地 API Key</h3>
    <p style="margin:0 0 12px;color:var(--muted);font-size:12px">当前还是默认 Key，任何人都能调用你的网关。改一个自己的更安全。</p>
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

# --- 4) Patch importSetupKeys to show probe results ---
PROBE_HELPER = r'''
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

async function syncWorkBuddy(){
  try{
    const r = await fetch("/api/integrations/workbuddy", { method:"POST", headers: authHeaders() });
    const j = await r.json().catch(()=>({}));
    if (!r.ok) throw new Error(j.detail || "sync failed");
    toast("已同步 WorkBuddy：" + (j.path || ""));
    return true;
  }catch(e){
    toast("同步失败：" + (e.message||"未知错误"), true);
    return false;
  }
}

function cursorSnippet(base, key){
  return JSON.stringify({
    "dashuai-gateway": {
      name: "大帅网关",
      baseUrl: base,
      apiKey: key,
      models: Object.keys(state.routes || {daily:1, fast:1})
    }
  }, null, 2);
}
'''

if "function renderProbe(" not in text:
    text = text.replace("function go(page){", PROBE_HELPER + "\nfunction go(page){", 1)

# Enhance importSetupKeys probe loop to call renderProbe
if "renderProbe(results)" not in text:
    text = text.replace(
        """    for (const p of state.providers) {
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
    go("connect");""",
        """    const results = [];
    for (const p of state.providers) {
      if (!(p.enabled && keyReady(p.api_key))) continue;
      try {
        const rr = await fetch("/api/probe", {
          method: "POST",
          headers: authHeaders(),
          body: JSON.stringify({ name: p.name }),
        });
        const jj = await rr.json().catch(() => ({}));
        results.push({
          name: p.name,
          ok: !!jj.ok,
          ms: jj.latency_ms || jj.latency || 0,
          detail: jj.ok ? "连通正常" : (jj.detail || jj.error || "探测失败"),
        });
      } catch (e) {
        results.push({ name: p.name, ok: false, ms: 0, detail: String(e.message || e) });
      }
    }
    renderProbe(results);
    await refresh();
    go("connect");""",
        1,
    )

# Wire new buttons before firstRun / end
WIRE = r'''
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
'''

if 'id="btnImportSync")).onclick' not in text and 'btnImportSync")).onclick' not in text:
    # insert before firstRunSetup or at end of script
    anchor = "if ($(\"#btnImportKeys\")) $(\"#btnImportKeys\").onclick = importSetupKeys;"
    if anchor in text:
        text = text.replace(anchor, anchor + "\n" + WIRE, 1)
    else:
        text = text.replace("</script>", WIRE + "\n</script>", 1)

HTML.write_text(text, encoding="utf-8")

# verify
script = HTML.read_text(encoding="utf-8")
a = script.find("<script>") + 8
b = script.find("</script>", a)
js = script[a:b]
try:
    compile(js, "index.html", "exec")
    print("COMPILE OK")
except SyntaxError as e:
    print("SYNTAX FAIL", e)
    # show around go
    i = js.find("function go")
    print(js[i : i + 300])
    raise

print("go ok", "function go(page){" in js and "const PRESETS" in js)
print("PRESETS inside go?", bool(re.search(r"function go\(page\)\{\s*const PRESETS", js)))
print("btnImportKeys", "btnImportKeys" in js)
print("renderProbe", "renderProbe" in js)
print("bytes", HTML.stat().st_size)
