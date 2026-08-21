# AGENTS.md — free-llm-gateway

本地 OpenAI 兼容多厂商网关。无 license / 无过期。

## 结构

- `gateway/` — FastAPI 服务：鉴权、路由、上游转发
- `data/*.example.json` — 配置模板；真实 Key 写入 `data/*.json`（gitignore）
- `web/` — 简易状态页
- `start.cmd` — Windows 一键启动

## 约定

- 默认只监听 `127.0.0.1:8010`
- 客户端 Base URL 填 `http://127.0.0.1:8010/v1`
- 勿提交 `providers.json` 里的真实密钥
