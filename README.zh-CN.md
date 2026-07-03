# GE Observability

> **语言**: [English](./README.md) · 中文

![总览页 — 中文](./docs/screenshots/overview-zh.png)

**Gemini Enterprise** 用户采纳 / 治理 / 审计的自部署 dashboard，
Cloud Logging → BigQuery → React + FastAPI 全套打通。

回答的问题：
- 谁是 **POWER_USER / ACTIVE_CONSUMER / TRIAL / LURKER**？
- 谁建了哪个 **agent / engine / data store**？
- 用户问了什么 **prompt**，模型怎么答的？
- 哪个 **engine** 最受欢迎？
- 哪些 **seat** 占了但没用？
- **Deep Research / NotebookLM / 自建 agent** 各调用了多少次，谁调的，具体哪几次？

---

## 页面

| 页面 | 内容 |
|---|---|
| **总览** | DAU 趋势 · persona 分布饼图 · KPI 卡片 · engine 列表 · 数据新鲜度 |
| **用户 deep dive (员工目录)** | 可搜索 + 可排序 + 可过滤的员工列表，每人 × 每个 feature 一目了然 |
| **用户 deep dive (单人)** | 单用户全部活动；每个数字可点开看具体哪几次 |
| **Agent 看板** | 按 agent 聚合 (Deep Research / NotebookLM / custom)，用户分布 + 事件 timeline |
| **对话内容** | Prompt + response 气泡，按"有响应 / 仅 prompt" 过滤 |
| **Data Access** | 每个 method 桶展示 (含 NotebookLM / A2A / Deep Research 列) |
| **文件与 Agent** | Session 文件活动 + 自建 agent 入口浏览 |
| **Builder 排行** | 谁创建/更新/删除了哪些资源 |
| **管理操作时间线** | Path 3 audit log 时间线 |
| **设置** | Quota 配置 + snapshot 刷新状态 + 数据源配置 |

---

## 架构

```
┌──────────────────────────────────────────────────────────────────┐
│ 1) GE 用户操作                                                    │
│    真人 → GE 控制台 UI    /    SA → REST → Discovery Engine        │
└──────────────────────────────────┬───────────────────────────────┘
                                   ↓
┌──────────────────────────────────────────────────────────────────┐
│ 2) Discovery Engine emit 日志到 Cloud Logging                     │
│                                                                  │
│   Path 2 — 业务日志 (在 GE 控制台开关控制)：                       │
│   • discoveryengine.googleapis.com/gemini_enterprise_user_activity │
│   • discoveryengine.googleapis.com/gen_ai.user.message           │
│   • discoveryengine.googleapis.com/gen_ai.choice                 │
│                                                                  │
│   Path 3 — 审计日志 (GCP 平台层)：                                 │
│   • cloudaudit.googleapis.com/activity     (默认开)               │
│   • cloudaudit.googleapis.com/data_access  (要手动启)             │
└──────────────────────────────────┬───────────────────────────────┘
                                   ↓ Logs Router sink
┌──────────────────────────────────────────────────────────────────┐
│ 3) BigQuery dataset: ge_observability                            │
│    • 5 张原始表 (sink 自动落)                                     │
│    • 18 个分析 view (v_*)                                         │
│    • 18 个 snapshot 表 (s_*, 每 6h 物化一次)                       │
│    • engine_metadata + resources_alive + quota_config            │
└──────────────────────────────────┬───────────────────────────────┘
                                   ↓ google-cloud-bigquery
┌──────────────────────────────────────────────────────────────────┐
│ 4) FastAPI on Cloud Run (IAM 限定 invoker)                        │
│    GET /api/v/{view}?origin=&engine_id=&live=                    │
│    GET /api/user/{email}      — 单用户 deep dive                  │
│    GET /api/agent/{agent_id}  — 单 agent 聚合                     │
│    POST /api/refresh          — 重新物化 snapshot                 │
└──────────────────────────────────┬───────────────────────────────┘
                                   ↓ fetch()
┌──────────────────────────────────────────────────────────────────┐
│ 5) React 18 + Vite + Tailwind (中/EN 双语) → 浏览器                │
└──────────────────────────────────────────────────────────────────┘
```

---

## 部署到自己的 GCP 项目

**一键** (前提：`gcloud` 已认证、装了 `terraform`、目标项目里已有 GE engine)：

```bash
git clone https://github.com/coolsocket/gemini-enterprise-observability
cd gemini-enterprise-observability
make deploy PROJECT=my-project REGION=us-central1
```

按顺序跑：

1. `terraform apply` — enable 9 个 API + BQ dataset + 5 张 metadata 表 + sink + audit config + service account + Cloud Run + 可选 Scheduled Query
2. `gcloud builds submit` — build + push container image
3. `apply_views.py` — render + apply 18 个 BigQuery view (模板用 `{{PROJECT}}` / `{{DATASET}}` / `{{SIM_PATTERN}}` 占位)
4. `bootstrap.py` — 通过 Discovery Engine API 拉 `engine_metadata` / `datastore_metadata` / `resources_alive`，seed `quota_config`

剩下 **2 个手工步骤**：

1. **GE 控制台 toggle**（每个 engine 都要开）— 详见 [`docs/GE_CONSOLE_SETUP.md`](./docs/GE_CONSOLE_SETUP.md)：
   - Enable OpenTelemetry Instrumentation (生成 trace ID)
   - Enable Prompt & Response Logging (写 `gen_ai.user.message` 和 `gen_ai.choice`)
   - Enable Feedback (可选)
2. **加 invoker 权限** — 编辑 `terraform/terraform.tfvars` 的 `iap_invokers = ["user:alice@example.com", …]`，再跑一次 `make tf-apply`

打开 dashboard：

```bash
gcloud run services proxy ge-observability --port 8080 --region us-central1
open http://localhost:8080
```

### 分步走 (`make deploy` 中途失败时)

```bash
make tf-plan   PROJECT=my-project    # 预览
make tf-apply  PROJECT=my-project    # 真建基础设施
# (手动开 GE 控制台 toggle，等几分钟让第一批日志落下来)
make image     PROJECT=my-project    # build + push container
make views     PROJECT=my-project    # apply 18 view
make bootstrap PROJECT=my-project    # 拉 metadata
```

---

## 本地开发

```bash
make install                              # 装 python venv + npm 依赖
make api-run                              # FastAPI 起在 http://127.0.0.1:8000
# 另开一个 terminal:
cd apps/web && npm run dev                # Vite HMR
```

或者单进程 preview (build 完的前端由 FastAPI 直接服务)：

```bash
make serve PORT=8011
ssh -L 8011:127.0.0.1:8011 <remote-host>  # 跑在远程机器上的话
open http://localhost:8011
```

---

## 仓库结构

```
ge-observability-service/
├── apps/
│   ├── api/                              # FastAPI 后端
│   │   ├── main.py
│   │   └── requirements.txt
│   └── web/                              # React 18 + Vite + Tailwind 前端
│       ├── src/pages/                    # Overview · UserDeepDive · Agents · Conversations · …
│       ├── src/components/               # Sidebar · Header · Card · DataTable · Brand
│       └── src/i18n.tsx                  # 中/EN 词典
├── infra/
│   ├── sql_templates/views.sql.tmpl      # 18 个 view，{{PROJECT}} / {{DATASET}} / {{SIM_PATTERN}} 占位
│   └── scripts/
│       ├── apply_views.py                # render + apply view 到 BigQuery
│       └── bootstrap.py                  # 拉 engine/datastore/agent 元数据
├── terraform/
│   ├── main.tf                           # API + dataset + sink + audit + SA + Cloud Run + Scheduled Query
│   ├── variables.tf
│   ├── terraform.tfvars.example
│   ├── snapshot_refresh.sql.tftpl        # 每 6h 重物化 query 模板
│   └── README.md
├── docs/
│   ├── RUNBOOK.md                        # 运维任务 + 故障排查
│   └── GE_CONSOLE_SETUP.md               # GE 管理员需要点的 3 个 toggle
├── Dockerfile                            # 多阶段：node build + python runtime
├── Makefile                              # install / serve / dev / deploy / tf-* / image / views / bootstrap
└── README.md                             # ← 这文件
```

---

## 已知数据边界

Dashboard 暴露了 GE 真正 emit 的全部信号。下面是**抓不到**的，以及原因：

1. **多模态**：`streamAssist` 不接受 `inlineData`，图片/文件走单独 session-file 流程。Dashboard 把文件活动以 `session_files` 计数展示，但**看不到上传了什么内容**。

2. **trace_id 配对**：只有 `v1alpha` (REST) 聊天会产生配对的 `gen_ai.choice` 日志。UI 走的是 `v1main`，写 `user_activity` 但**不写 `choice`** → GE 网页发起的对话都是 `join_status='no_response'`。对话内容页用"✓有响应 / 仅 prompt" filter 让这一点一目了然。

3. **Deep Research (AsyncAssist)**：GE Deep Research 走 `AssistantService.AsyncAssist` + `ReadAsyncAssist`，这些调用进 `cloudaudit_googleapis_com_data_access`，所以 dashboard 能 per-user/engine 计数。**但 prompt + response 文本不被 emit** — 跟 UI 同源限制。要看实际研究内容只能去 GE 后台的 Deep Research 任务列表。

4. **NotebookLM Enterprise**：真实方法名在 `google.cloud.notebooklm.v1main.*` 命名空间下（**不是**官方文档暗示的 `v1alpha` — 实测 UI emit 的是 `v1main`）。观察到 6 个 service：`NotebookService` / `SourceService` / `NoteService` / `ArtifactService` / `AudioOverviewService` / `AccountService`。全部在 `serviceName="discoveryengine.googleapis.com"` 下面。桶分成 `notebooklm_{notebook,content,audio}_ops` 三列。NotebookLM 这一行 `engine_id` 是 NULL，因为 notebook resource name 不带 `/engines/`。

   ⚠ Service account **不能** 通过 REST 触发 NotebookLM 或 Deep Research — 这些 method 只响应 UI 已认证 session。要让 dashboard 有数据必须真人用 GE 网页操作。

5. **A2A agent 调用**：marketplace agent + custom agent 通过 A2A 协议调用 → 走 `assistants.agents.a2a.v1.{message,tasks}.*`，桶为 `a2a_invocations`。暂时没按 agent 细分。

6. **其他内置 agent (Idea Generation / Co-Scientist / AlphaEvolve)**：这些走 `AssistantService.StreamAssist`，**method 名上跟普通 chat 区分不开**。要拆开得开 DATA_WRITE audit log + request body capture。

7. **Custom agent — 只能看导航不知调用**：用户点击 custom agent 详情页时，`UserEventService.WriteUserEvent` 会带 `agentinfo.{agentid, name}` — 这告诉我们*谁点过哪个 agent*，但不知道有没有真触发调用。真调用要么走 StreamAssist (跟 chat 混)，要么走 A2A (在 `a2a_invocations` 里)。

8. **Create 事件缺 resource ID**：`CreateAgent` audit log 的 `resourceName` 是 parent (`assistants/default_assistant`) 不是新 agent ID。所以"哪个 user 建了哪些 alive 资源"没法追溯。总览页用 `ListAgents` API 直接查全系统 alive 数。

9. **Prompt PII**：`v_conversations` 对 email / 手机号 / ID 数字 / 信用卡数字做正则脱敏。**不是完整 DLP** — 长文本 PII (人名、地址) 不脱。生产环境上 Cloud DLP。

10. **没有 seat/license 公开 API**：`purchased_seats` 是 `quota_config` 里手工配的值。`claimed` 用近 30 天活跃 actor 算。

---

## 鉴权

Cloud Run 用 `--no-allow-unauthenticated` 启动，只有 `roles/run.invoker` 持有者能命中。

- **本地浏览器临时访问**：
  ```bash
  gcloud run services proxy ge-observability --port 8080 --region us-central1
  ```
- **生产 SSO**：通过 Cloud Console (Security → Identity-Aware Proxy) 加 Cloud IAP，再把组加到 `terraform/terraform.tfvars` 的 `iap_invokers`。

---

## 运维任务

- **手动刷 snapshot**：dashboard header 点 ⟳ (或 `POST /api/refresh`)
- **定时刷新**：BigQuery Scheduled Query 每 6h 跑 (在 `terraform.tfvars` 设 `enable_scheduled_refresh = true`，前提是 `make views` 已经跑过至少一次)
- **加模拟用户**：见 [`docs/RUNBOOK.md#simulate-users`](./docs/RUNBOOK.md)
- **接入新 engine**：再跑一次 `make bootstrap PROJECT=…` 同步 `engine_metadata`

---

## License

MIT — 见 [`LICENSE`](./LICENSE). Built by Claude Code (Opus). 欢迎贡献。
