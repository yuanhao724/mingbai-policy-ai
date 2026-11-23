# 部署与 GitHub 发布

## 本地运行

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000。

## Docker

```powershell
docker compose up --build
```

或：

```powershell
docker build -t mori:local .
docker run --rm -p 8000:8000 -v mori-data:/app/backend/data mori:local
```

当前开发机的 Docker daemon 未启动，所以本地没有实际构建镜像；CI 里包含
Docker build job。

## 部署到云平台

目标是任意支持 Docker 或 Python Web 服务的平台，例如 Render、Railway、
Fly.io 或一台 Linux 云主机。

必填环境变量：

```dotenv
MORI_DB_PATH=/app/backend/data/mori.db
MORI_RATE_LIMIT_PER_MINUTE=240
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
MORI_MODEL=gpt-4o-mini
```

- 不配置 `OPENAI_API_KEY` 时使用本地模式。
- 必须挂载持久化磁盘到 `/app/backend/data`，否则重启后 SQLite 数据会丢失。
- 健康检查使用 `GET /api/ready`。
- 对外暴露端口 `8000`。

## 发布前检查

```powershell
cd backend
$env:MORI_STREAM_DELAY = "0"
python -m unittest discover -s tests -v
python eval/run_eval.py --check
```

当前质量门：

- 100 条评测：80 条可回答 + 20 条跨域/近域拒答。
- Hit@3 100%，引用有效/覆盖 100%，引用支撑 99.6%，拒答 100%。
- 27 个自动化测试。

## GitHub 仓库设置

建议仓库名：`mingbai-policy-ai`

建议简介：

> Policy-to-action AI assistant with citations, 100-question evaluation, human review, and audit logs.

建议 topics：

`ai` `llm` `rag` `fastapi` `knowledge-base` `policy` `python`
`evaluation` `human-in-the-loop` `observability`

发布后把 README、简历和私信话术里的「代码与 Demo 可提供」替换成：

- GitHub 仓库地址
- 公开 Demo 地址

## README 截图

`docs/screenshots/` 已包含：

- `home-desktop.png`
- `workbench-desktop.png`
- `eval-desktop.png`
- `review-desktop.png`
- `case-study-desktop.png`
- 对应的移动端截图

如果改了 UI，重新截图后再发布，避免 README 与真实页面不一致。
