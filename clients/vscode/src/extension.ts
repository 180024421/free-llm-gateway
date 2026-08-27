import * as vscode from "vscode";

const ROUTE_OPTIONS = [
  { id: "日常", label: "日常" },
  { id: "快速", label: "快速" },
  { id: "复杂", label: "复杂" },
  { id: "小说", label: "小说" },
  { id: "代码", label: "代码" },
  { id: "识图", label: "识图" },
  { id: "翻译", label: "翻译" },
  { id: "总结", label: "总结" },
  { id: "推理", label: "推理" },
  { id: "长文", label: "长文" },
  { id: "Agent", label: "Agent" },
];

const MAX_SESSION = 10;

type ChatMsg = { role: "user" | "assistant"; content: string };

function cfg() {
  const c = vscode.workspace.getConfiguration("dashuai");
  return {
    baseUrl: (c.get<string>("baseUrl") || "http://127.0.0.1:8010/v1").replace(/\/$/, ""),
    apiKey: c.get<string>("apiKey") || "sk-local-change-me",
    model: c.get<string>("model") || "日常",
    dashboardUrl: c.get<string>("dashboardUrl") || "http://127.0.0.1:8010/ui/",
    stream: c.get<boolean>("stream") !== false,
  };
}

class ChatViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "dashuai.chatView";
  private session: ChatMsg[] = [];
  private view?: vscode.WebviewView;

  constructor(private readonly ctx: vscode.ExtensionContext) {}

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    this.view = webviewView;
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.html = this.html(webviewView.webview);
    webviewView.webview.onDidReceiveMessage(async (msg) => {
      if (msg?.type === "clear") {
        this.session = [];
        webviewView.webview.postMessage({ type: "cleared" });
        return;
      }
      if (msg?.type === "chat") {
        const prompt = String(msg.prompt || "").trim();
        if (!prompt) return;
        this.session.push({ role: "user", content: prompt });
        this.trimSession();
        try {
          const answer = await this.chatWithStream(prompt, (delta) => {
            webviewView.webview.postMessage({ type: "delta", text: delta });
          });
          this.session.push({ role: "assistant", content: answer });
          this.trimSession();
          webviewView.webview.postMessage({ type: "done", text: answer });
        } catch (e: any) {
          const err = `错误：${e?.message || e}`;
          webviewView.webview.postMessage({ type: "done", text: err, error: true });
        }
        return;
      }
      if (msg?.type === "ready") {
        const c = cfg();
        webviewView.webview.postMessage({
          type: "config",
          baseUrl: c.baseUrl,
          model: c.model,
          routes: ROUTE_OPTIONS.map((r) => r.id),
          history: this.session.slice(-MAX_SESSION),
        });
      }
    });
  }

  private trimSession() {
    if (this.session.length > MAX_SESSION) {
      this.session = this.session.slice(-MAX_SESSION);
    }
  }

  private async chatWithStream(
    prompt: string,
    onDelta: (chunk: string) => void
  ): Promise<string> {
    const c = cfg();
    const messages = [
      ...this.session.slice(0, -1).map((m) => ({ role: m.role, content: m.content })),
      { role: "user" as const, content: prompt },
    ].slice(-MAX_SESSION);

    if (!c.stream) {
      const text = await chatOnce(prompt, messages);
      if (text) onDelta(text);
      return text;
    }
    return chatStream(prompt, c, onDelta, messages);
  }

  private html(webview: vscode.Webview): string {
    const csp = webview.cspSource;
    return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${csp} 'unsafe-inline'; script-src ${csp} 'unsafe-inline';" />
<style>
  body{font-family:var(--vscode-font-family);color:var(--vscode-foreground);margin:0;padding:10px;background:var(--vscode-sideBar-background)}
  #log{height:calc(100vh - 170px);overflow:auto;display:flex;flex-direction:column;gap:8px}
  .bubble{padding:8px 10px;border-radius:10px;line-height:1.5;white-space:pre-wrap}
  .user{background:var(--vscode-button-background);color:var(--vscode-button-foreground);align-self:flex-end;max-width:92%}
  .bot{background:var(--vscode-input-background);border:1px solid var(--vscode-input-border);align-self:flex-start;max-width:92%}
  .meta{font-size:11px;opacity:.7;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;gap:8px}
  .row{display:flex;gap:6px;margin-top:8px}
  textarea{flex:1;min-height:64px;resize:vertical;background:var(--vscode-input-background);color:var(--vscode-input-foreground);border:1px solid var(--vscode-input-border);border-radius:8px;padding:8px}
  button{background:var(--vscode-button-background);color:var(--vscode-button-foreground);border:0;border-radius:8px;padding:0 12px;cursor:pointer}
  button.ghost{background:transparent;border:1px solid var(--vscode-input-border);color:var(--vscode-foreground);font-size:11px;padding:2px 8px}
</style>
</head>
<body>
  <div class="meta">
    <span id="meta">大帅网关 · 连接中…</span>
    <button class="ghost" type="button" id="clear">清空对话</button>
  </div>
  <div id="log"></div>
  <div class="row">
    <textarea id="prompt" placeholder="问点什么…"></textarea>
    <button id="send">发送</button>
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    const log = document.getElementById('log');
    const meta = document.getElementById('meta');
    const prompt = document.getElementById('prompt');
    let streamingEl = null;
    function add(role, text){
      const d=document.createElement('div');
      d.className='bubble '+(role==='user'?'user':'bot');
      d.textContent=text;
      log.appendChild(d);
      log.scrollTop=log.scrollHeight;
      return d;
    }
    function resetLog(history){
      log.innerHTML='';
      streamingEl=null;
      (history||[]).forEach(m => add(m.role==='user'?'user':'bot', m.content||''));
    }
    document.getElementById('clear').onclick=()=>{
      vscode.postMessage({type:'clear'});
    };
    document.getElementById('send').onclick=()=>{
      const t=prompt.value.trim();
      if(!t) return;
      add('user', t);
      prompt.value='';
      streamingEl = add('bot', '');
      vscode.postMessage({type:'chat', prompt:t});
    };
    window.addEventListener('message', ev=>{
      const m=ev.data||{};
      if(m.type==='config'){
        meta.textContent='大帅网关 · '+m.model+' · '+m.baseUrl;
        if (m.history && m.history.length) resetLog(m.history);
      }
      if(m.type==='cleared'){ resetLog([]); }
      if(m.type==='delta'){
        if(!streamingEl) streamingEl = add('bot', '');
        streamingEl.textContent = (streamingEl.textContent||'') + (m.text||'');
        log.scrollTop=log.scrollHeight;
      }
      if(m.type==='done'){
        if(!streamingEl) streamingEl = add('bot', '');
        // Prefer full text on done (non-stream path); keep appended if already streaming
        if (m.text && (!streamingEl.textContent || m.error)) streamingEl.textContent = m.text;
        else if (m.text && streamingEl.textContent.length < m.text.length) streamingEl.textContent = m.text;
        streamingEl = null;
      }
    });
    vscode.postMessage({type:'ready'});
  </script>
</body>
</html>`;
  }
}

async function fetchLicenseStatus(): Promise<string> {
  const c = cfg();
  const root = c.baseUrl.replace(/\/v1\/?$/, "");
  const headers: Record<string, string> = { Accept: "application/json" };
  if (c.apiKey) headers.Authorization = `Bearer ${c.apiKey}`;
  const r = await fetch(`${root}/api/license/status?refresh=1`, { headers });
  const j: any = await r.json().catch(() => ({}));
  if (!r.ok) {
    throw new Error(j?.detail?.message || j?.message || `HTTP ${r.status}`);
  }
  if (!j.logged_in) return "大帅授权: 未登录（请打开桌面端登录激活）";
  if (j.frozen) return "大帅授权: 已冻结";
  if (!j.valid) return `大帅授权: ${j.message || "无效"}`;
  const parts: string[] = ["大帅授权"];
  if (j.plan_label) parts.push(String(j.plan_label));
  if (j.token_unlimited) parts.push("Token不限");
  else if (j.token_remaining != null) parts.push(`剩余${j.token_remaining}`);
  if (j.time_unlimited) parts.push("不限时");
  else if (j.expire_at) parts.push(`至${String(j.expire_at).slice(0, 10)}`);
  if (j.low_balance) parts.push("余量不足");
  return parts.join(" · ");
}

async function chatOnce(
  prompt: string,
  messages?: { role: string; content: string }[]
): Promise<string> {
  const c = cfg();
  const res = await fetch(`${c.baseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${c.apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: c.model,
      messages: messages?.length
        ? messages
        : [{ role: "user", content: prompt }],
      stream: false,
      temperature: 0.7,
    }),
  });
  if (res.status === 402) {
    throw new Error("未激活或 Token 不足，请打开大帅网关控制台购买/激活卡密");
  }
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`${res.status} ${t.slice(0, 300)}`);
  }
  const data: any = await res.json();
  return data?.choices?.[0]?.message?.content || JSON.stringify(data);
}

async function chatStream(
  prompt: string,
  c: ReturnType<typeof cfg>,
  onDelta?: (chunk: string) => void,
  messages?: { role: string; content: string }[]
): Promise<string> {
  const res = await fetch(`${c.baseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${c.apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: c.model,
      messages: messages?.length
        ? messages
        : [{ role: "user", content: prompt }],
      stream: true,
      temperature: 0.7,
    }),
  });
  if (res.status === 402) {
    throw new Error("未激活或 Token 不足，请打开大帅网关控制台购买/激活卡密");
  }
  if (!res.ok || !res.body) {
    const t = await res.text();
    throw new Error(`${res.status} ${t.slice(0, 300)}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";
  let out = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() || "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      const payload = trimmed.slice(5).trim();
      if (payload === "[DONE]") continue;
      try {
        const obj = JSON.parse(payload);
        const delta = obj?.choices?.[0]?.delta?.content;
        if (typeof delta === "string" && delta) {
          out += delta;
          if (onDelta) onDelta(delta);
        }
      } catch {
        /* ignore partial json */
      }
    }
  }
  return out || "(空响应)";
}

export function activate(context: vscode.ExtensionContext) {
  const provider = new ChatViewProvider(context);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(ChatViewProvider.viewType, provider)
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("dashuai.openChat", async () => {
      await vscode.commands.executeCommand("dashuai.chatView.focus");
    })
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("dashuai.openDashboard", () => {
      vscode.env.openExternal(vscode.Uri.parse(cfg().dashboardUrl));
    })
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("dashuai.copyBaseUrl", async () => {
      await vscode.env.clipboard.writeText(cfg().baseUrl);
      vscode.window.showInformationMessage(`已复制：${cfg().baseUrl}`);
    })
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("dashuai.pickRoute", async () => {
      const pick = await vscode.window.showQuickPick(
        ROUTE_OPTIONS.map((r) => ({ label: r.label, id: r.id })),
        { placeHolder: "选择用途路由" }
      );
      if (!pick) return;
      const c = vscode.workspace.getConfiguration("dashuai");
      await c.update("model", pick.id, vscode.ConfigurationTarget.Global);
      vscode.window.showInformationMessage(`已切换模型：${pick.id}`);
    })
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("dashuai.showLicense", async () => {
      try {
        const text = await fetchLicenseStatus();
        vscode.window.showInformationMessage(text);
      } catch (e: any) {
        vscode.window.showErrorMessage(`授权查询失败：${e?.message || e}`);
      }
    })
  );

  const licenseBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 80);
  licenseBar.command = "dashuai.showLicense";
  licenseBar.text = "大帅授权: …";
  licenseBar.tooltip = "点击查看网关授权状态（与桌面端同一账号权益）";
  licenseBar.show();
  context.subscriptions.push(licenseBar);
  const refreshLicense = async () => {
    try {
      const text = await fetchLicenseStatus();
      licenseBar.text = text.length > 28 ? text.slice(0, 28) + "…" : text;
      licenseBar.tooltip = text;
    } catch {
      licenseBar.text = "大帅授权: 未连接";
    }
  };
  void refreshLicense();
  const timer = setInterval(() => void refreshLicense(), 60000);
  context.subscriptions.push({ dispose: () => clearInterval(timer) });

  context.subscriptions.push(
    vscode.commands.registerCommand("dashuai.applyCursorHint", () => {
      const c = cfg();
      const routes = ROUTE_OPTIONS.map((r) => r.id).join(" / ");
      const md = [
        "# 大帅网关 · Cursor / Continue 接入",
        "",
        "## Cursor 自定义模型",
        `- Base URL: \`${c.baseUrl}\``,
        `- API Key: \`${c.apiKey}\``,
        `- Model: \`${c.model}\`（可选：${routes}）`,
        "",
        "## Continue (VS Code)",
        "```json",
        JSON.stringify(
          {
            models: [
              {
                title: "大帅网关",
                provider: "openai",
                model: c.model,
                apiBase: c.baseUrl,
                apiKey: c.apiKey,
              },
            ],
          },
          null,
          2
        ),
        "```",
      ].join("\n");
      vscode.workspace
        .openTextDocument({ content: md, language: "markdown" })
        .then((doc) => vscode.window.showTextDocument(doc));
    })
  );
}

export function deactivate() {}
