# Free LLM Gateway

无授权、无过期、可自托管的 **OpenAI 兼容模型网关**。  
聚合多家上游（NVIDIA / ModelScope / 任意 OpenAI 兼容接口），智能择优 + 故障切换，给 **WorkBuddy**、ChatBox、Cursor 自定义模型、自写脚本等统一一个本地入口。

> 本项目**不会**产生免费额度；「看起来无限」来自你自己注册的多家免费 Key 叠加与自动换路。

## 特性

- `GET /v1/models`、`POST /v1/chat/completions`（支持 stream）
- 路由组：`fast` / `daily` / `256k` / `1m`（可改 `data/routers.json`）
- 按健康分与权重选路，429/5xx/网络错误自动试下一个
- 简易熔断，避免死磕坏渠道
- 用量追加写入 `data/usage.jsonl`
- 本地面板：`http://127.0.0.1:8000/ui/`
- **无 license / 无试用倒计时 / 无联网激活**

## 快速开始（Windows）

```powershell
cd D:\project\free-llm-gateway
.\start.cmd
```

或手动：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy data\config.example.json data\config.json
copy data\providers.example.json data\providers.json
copy data\routers.example.json data\routers.json
# 编辑 data\providers.json 填入真实 API Key
python -m gateway
```

默认监听：`http://127.0.0.1:8010`（避免与其它本机网关抢 `8000`）

## 配置

| 文件 | 作用 |
|------|------|
| `data/config.json` | `local_api_key`、host/port、超时与重试 |
| `data/providers.json` | 上游：`base_url` / `api_key` / `models` / `weight` / `enabled` |
| `data/routers.json` | 虚拟模型名 → `candidates` 列表 |

`providers.json` 里 Key 仍是 `REPLACE_...` 或 `enabled: false` 的渠道会被跳过。

## 对接 WorkBuddy

在 WorkBuddy 自定义模型（或编辑 `~/.workbuddy/models.json`）例如：

```json
{
  "id": "daily",
  "name": "日常",
  "vendor": "Custom",
  "url": "http://127.0.0.1:8010/v1",
  "apiKey": "sk-local-change-me",
  "supportsToolCall": true,
  "supportsImages": true,
  "supportsReasoning": true,
  "maxInputTokens": 1048576,
  "maxOutputTokens": 32768
}
```

`apiKey` 必须与 `data/config.json` 的 `local_api_key` 一致。  
`id` 填路由组名（如 `daily` / `fast` / `256k`）或上游真实模型 id。

## 对接其它客户端

任何支持 OpenAI 兼容 API 的工具：

- Base URL：`http://127.0.0.1:8010/v1`
- API Key：本地 `local_api_key`
- Model：路由组名或上游模型名

curl 冒烟：

```powershell
curl http://127.0.0.1:8010/health
curl http://127.0.0.1:8010/v1/models -H "Authorization: Bearer sk-local-change-me"
```

## 安全说明

- 默认只绑 `127.0.0.1`。若改成 `0.0.0.0`，务必换强 `local_api_key` 并配合防火墙。
- 上游 Key 只放本机 `data/providers.json`（已 gitignore），勿提交仓库。

## 许可

MIT。可自由商用、修改、再分发。无激活、无到期。
