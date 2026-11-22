# 明白办事 · 运行与运维手册

## 本地运行

```powershell
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

或：

```powershell
./run.ps1
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

当前开发环境 Docker daemon 未启动，因此本地没有实际构建镜像。Dockerfile 和 CI 中的 build job 用于在 CI 环境验证。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 空 | 为空时使用本地模式 |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | 兼容 OpenAI 协议的网关 |
| `MORI_MODEL` | `gpt-4o-mini` | 在线模型 |
| `MORI_DB_PATH` | `backend/data/mori.db` | SQLite 路径 |
| `MORI_RATE_LIMIT_PER_MINUTE` | `240` | 单 IP 限流 |
| `MORI_LOG_LEVEL` | `INFO` | 日志级别 |
| `MORI_STREAM_DELAY` | `0.012` | 本地流式输出间隔，测试时设为 0 |

## 健康检查

```bash
curl http://127.0.0.1:8000/api/live
curl http://127.0.0.1:8000/api/ready
```

- `/api/live`：进程存活。
- `/api/ready`：数据库可连接。

Docker HEALTHCHECK 使用 `/api/ready`。

## 指标

```bash
curl http://127.0.0.1:8000/api/metrics
```

包含：

- `mori_app_info`
- `mori_http_requests_total{method,path,status}`
- `mori_http_request_duration_seconds_bucket`
- `mori_http_request_duration_seconds_sum`
- `mori_http_request_duration_seconds_count`

路径中的动态 ID 已经归一化为 `:id`，避免高基数标签。

## 日志

每个 API 请求输出一行 JSON：

```json
{"event":"http_request","request_id":"...","method":"GET","path":"/api/health","status":200,"duration_ms":1.2}
```

请求头会返回 `X-Request-ID`，可以从前端错误、网关日志和后端日志串起来。

日志不记录用户问题全文和答案全文，避免把政策查询内容写入日志。

## 限流

- 默认 240 请求/分钟/IP，令牌桶实现。
- `/api/health`、`/api/live`、`/api/ready`、`/api/metrics` 不限流。
- 超限返回 429 和 `Retry-After: 60`。
- 进程内限流只适合单实例演示；生产用 Redis 或 API Gateway。

## 安全响应头

所有响应包含：

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy`
- `Content-Security-Policy`

CSP 目前允许 inline style/script，因为页面有内联样式和脚本。生产可以进一步拆分为外部资源并收紧 CSP。

## 备份与恢复

SQLite 备份示例：

```python
import sqlite3

source = sqlite3.connect("backend/data/mori.db")
target = sqlite3.connect("backup/mori-backup.db")
source.backup(target)
source.close()
target.close()
```

恢复：停止服务，替换 `mori.db`，确认权限后重启。生产建议每日备份并保留 7 到 30 天。

## 发布流程

1. 运行 `python -m unittest discover -s tests -v`。
2. 运行 `python eval/run_eval.py --check`。
3. 构建 Docker 镜像。
4. 在 staging 跑 `/api/ready` 和评测。
5. 灰度 10% 流量。
6. 观察 5xx、P95、429、审核队列。
7. 全量发布。

## 事故处理

### 5xx 升高

1. 用 `X-Request-ID` 查日志。
2. 检查 `/api/ready` 和数据库连接。
3. 检查最近部署和模型网关。
4. 必要时切回本地模式或回滚。

### 429 升高

1. 检查是否被爬虫或异常客户端刷接口。
2. 检查单 IP 请求量。
3. 临时提高阈值或加边缘限流规则。

### 回答质量下降

1. 运行 `python eval/run_eval.py --check`。
2. 对比 Hit@1 / Hit@3、引用支撑率、拒答准确率。
3. 检查知识库版本和切块配置。
4. 回滚政策版本或模型配置。

## 生产化清单

- [ ] Postgres 替代 SQLite。
- [ ] Redis 或网关限流。
- [ ] SSO / RBAC / 审核队列。
- [ ] 真实政策库和版本管理。
- [ ] 对象存储和异步解析任务。
- [ ] 集中日志、Prometheus、Grafana、告警。
- [ ] 审计日志不可篡改和保留策略。
- [ ] 真实社区试点和人工抽检。
