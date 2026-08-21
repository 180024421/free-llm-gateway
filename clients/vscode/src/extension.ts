import * as vscode from "vscode";

function cfg() {
  const c = vscode.workspace.getConfiguration("dashuai");
  return {
    baseUrl: (c.get<string>("baseUrl") || "http://127.0.0.1:8010/v1").replace(/\/$/, ""),
    apiKey: c.get<string>("apiKey") || "sk-local-change-me",
    model: c.get<string>("model") || "daily",
    dashboardUrl: c.get<string>("dashboardUrl") || "http://127.0.0.1:8010/ui/",
  };
}

class ChatViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "dashuai.chatView";

  constructor(private readonly ctx: vscode.ExtensionContext) {}

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.html = this.html(webviewView.webview);
    webviewView.webview.onDidReceiveMessage(async (msg) => {
      if (msg?.type === "chat") {
        try {
          const answer = await chatOnce(String(msg.prompt || ""));
          webviewView.webview.postMessage({ type: "reply", text: answer });
        } catch (e: any) {
          webviewView.webview.postMessage({
            type: "reply",
            text: `错误：${e?.message || e}`,
          });
        }
      }
      if (msg?.type === "ready") {
        const c = cfg();
        webviewView.webview.postMessage({
          type: "config",
          baseUrl: c.baseUrl,
          model: c.model,
        });
      }
    });
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
  #log{height:calc(100vh - 120px);overflow:auto;display:flex;flex-direction:column;gap:8px}
  .bubble{padding:8px 10px;border-radius:10px;line-height:1.5;white-space:pre-wrap}
  .user{background:var(--vscode-button-background);color:var(--vscode-button-foreground);align-self:flex-end;max-width:92%}
  .bot{background:var(--vscode-input-background);border:1px solid var(--vscode-input-border);align-self:flex-start;max-width:92%}
  .meta{font-size:11px;opacity:.7;margin-bottom:8px}
  .row{display:flex;gap:6px;margin-top:8px}
  textarea{flex:1;min-height:64px;resize:vertical;background:var(--vscode-input-background);color:var(--vscode-input-foreground);border:1px solid var(--vscode-input-border);border-radius:8px;padding:8px}
  button{background:var(--vscode-button-background);color:var(--vscode-button-foreground);border:0;border-radius:8px;padding:0 12px;cursor:pointer}
</style>
</head>
<body>
  <div class="meta" id="meta">大帅网关 · 连接中…</div>
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
    function add(role, text){
      const d=document.createElement('div');
      d.className='bubble '+(role==='user'?'user':'bot');
      d.textContent=text;
      log.appendChild(d);
      log.scrollTop=log.scrollHeight;
    }
    document.getElementById('send').onclick=()=>{
      const t=prompt.value.trim();
      if(!t) return;
      add('user', t);
      prompt.value='';
      add('bot', '思考中…');
      vscode.postMessage({type:'chat', prompt:t});
    };
    window.addEventListener('message', ev=>{
      const m=ev.data||{};
      if(m.type==='config'){ meta.textContent='大帅网关 · '+m.model+' · '+m.baseUrl; }
      if(m.type==='reply'){
        const bots=[...log.querySelectorAll('.bot')];
        if(bots.length) bots[bots.length-1].textContent=m.text;
        else add('bot', m.text);
      }
    });
    vscode.postMessage({type:'ready'});
  </script>
</body>
</html>`;
  }
}

async function chatOnce(prompt: string): Promise<string> {
  const c = cfg();
  const res = await fetch(`${c.baseUrl}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${c.apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: c.model,
      messages: [{ role: "user", content: prompt }],
      stream: false,
      temperature: 0.7,
    }),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`${res.status} ${t.slice(0, 300)}`);
  }
  const data: any = await res.json();
  return data?.choices?.[0]?.message?.content || JSON.stringify(data);
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
    vscode.commands.registerCommand("dashuai.applyCursorHint", () => {
      const c = cfg();
      const md = [
        "# 大帅网关 · Cursor / Continue 接入",
        "",
        "## Cursor 自定义模型",
        `- Base URL: \`${c.baseUrl}\``,
        `- API Key: \`${c.apiKey}\``,
        `- Model: \`${c.model}\`（或 fast / 256k / 1m）`,
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
