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

### 前置条件

开始之前请确认以下都到位:

**本地工具在 `PATH` 里**
- `gcloud` (Cloud SDK ≥ 460)
- `terraform` ≥ 1.5
- `python3` ≥ 3.11 + `pip`
- `npm` ≥ 8 (只有想改前端时需要;容器构建自己会装)
- `make`

**GCP 项目状态**
- 项目已建、billing 已开 (`gcloud beta billing projects link ...`)
- 你有 **Owner** 或 (Editor + Security Admin + Project IAM Admin) —— Terraform 要启用 API、授 role
- **Gemini Enterprise engine 已在目标项目里**(本仓库只观察,不建 GE)
- **Cloud Build API 预先启用** 好让 `make image` 第一次就通:`gcloud services enable cloudbuild.googleapis.com --project=<project>` (Terraform 会启,但顺序不对时先被这个卡)

**认证 (两个都要)**
- `gcloud auth login` —— Terraform + Cloud Build CLI 用
- `gcloud auth application-default login` —— Python 脚本 (`apply_views.py`, `bootstrap.py`) 和 FastAPI 后端都走 ADC

### 两阶段部署 (新项目推荐)

```bash
git clone https://github.com/coolsocket/gemini-enterprise-observability
cd gemini-enterprise-observability

# ---------- 阶段 A: 基础设施 + 镜像 + metadata ----------
make deploy-infra PROJECT=my-project REGION=us-central1
# 跑: terraform apply → gcloud builds submit → bootstrap.py

# ---------- 手工步骤 ----------
# GE Admin 控制台每个 engine 打开:
#   - OpenTelemetry Instrumentation      (生成 trace ID)
#   - Prompt & Response Logging          (写 gen_ai.* 日志)
#   - Feedback                           (可选)
# 详见 docs/GE_CONSOLE_SETUP.md
#
# 然后跑一点流量 (chat / deep research / 打开 notebook), 等 ~2-5 分钟让日志落到 BQ。

# ---------- 阶段 B: 建分析视图 ----------
make deploy-views PROJECT=my-project
```

为啥要拆:BigQuery 只在第一条匹配日志真正流进来的时候才创建 sink 目标表 (`cloudaudit_googleapis_com_data_access`, `discoveryengine_googleapis_com_*`)。`make deploy-views` **幂等** —— 可以随便重跑,还会告诉你哪几个 view 还在等源表,你就知道要等啥。

### 预览 dashboard

默认 **只本地跑** (`deploy_cloud_run = false`),不用为 Cloud Run 掏钱:

```bash
make serve PROJECT=my-project    # http://127.0.0.1:8000
```

要正式上 Cloud Run? 编辑 `terraform/terraform.tfvars`:

```hcl
deploy_cloud_run = true
iap_invokers     = ["user:alice@example.com", "group:ge-users@example.com"]
```

然后 `make tf-apply PROJECT=my-project`,打开:

```bash
gcloud run services proxy ge-observability --port 8080 --region us-central1
open http://localhost:8080
```

### 分步走 (debug)

```bash
make tf-plan   PROJECT=my-project    # 预览
make tf-apply  PROJECT=my-project    # 建基础设施 + Artifact Registry repo
make image     PROJECT=my-project    # build + push 镜像到 AR
make bootstrap PROJECT=my-project    # seed metadata
# (手动开 GE 控制台 toggle + 跑一点流量)
make views     PROJECT=my-project    # apply BQ view (重跑直到全部通过)
```

### 常见坑排查

**`make views` 报 "N view(s) skipped — waiting for log-sink tables"**
新项目上正常。列出来那些表 (`cloudaudit_googleapis_com_*`, `discoveryengine_googleapis_com_*`) 只有 Logs Router sink 实际送过一条记录后,BQ 才会建。开好 GE toggle、发几条 chat、等 ~2 分钟,再跑 `make views` —— 计数会一路减到 0。

**`gcloud builds submit` 在 `gcr.io/...` 报 `NOT_FOUND`**
`gcr.io` (Container Registry) 2024 年 2 月被 Google 废弃,之后建的 project 都没有。本仓库已经迁到 Artifact Registry —— 确保你在最新 `main` 上,`IMAGE` 变量解析出 `<region>-docker.pkg.dev/...`。先跑 `make tf-apply` 让 Terraform 建 AR repo,再跑 `make image`。

**Cloud Run URL 返回 403**
把调用方加到 `terraform.tfvars` 的 `iap_invokers` 里再 apply。没走 IAP 用 `roles/run.invoker`,走了 IAP 用 `principal://` 格式。还是 403 就看看 Cloud Run 是否要求 auth。

**`make views` 报 `Not found: Table quota_config`**
`make bootstrap` 跳了。那步创建 view 引用的 metadata 表 (`terraform apply` 也会幂等地建 —— 如果 apply 成功后还看到这个错,检查 `PROJECT` 和 `DATASET` 两边一致)。

**运行时 API 返回 BigQuery 查询 403**
runtime SA (`ge-observability-sa@…`) 要在 project 上有 `roles/bigquery.jobUser`,dataset 上有 `roles/bigquery.dataViewer`。Terraform 都授了 —— 如果你在 Terraform 外重命名了 dataset,重新 apply 让 IAM 跟上。

**`bootstrap.py` 报 `licenseConfigs` 404 或 403**
你的 GE 部署可能还没 `licenseConfigs` API 响应 (非常新的 tenant),或调用方缺 `roles/discoveryengine.viewer`。脚本会优雅降级 —— Quota 页面的 seat 数会 fallback 到 `quota_config` 表里已经存的值。

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

## 变更日志

用户可见行为、配额语义、dashboard 数据模型变化时请更新此列表。最新在上。完整详情看 `git log`。

- **2026-07-06** — 部署链条的 6 个修复(从零模拟部署时发现的 3 个 blocker + 后续打磨):(a) `apply_views.py` 现在把源表缺失分成三类 —— "等日志流"(可幂等重跑)、"Terraform 表缺失"(要跑 `tf-apply`)、"真错误"。(b) `bootstrap.py` 从 `subprocess("gcloud auth print-access-token")` 迁到 `google.auth.default()`,容器/CI 里不需要 gcloud CLI。(c) 镜像从被废弃的 `gcr.io/` 迁到 Artifact Registry (`<region>-docker.pkg.dev/...`),Terraform 新建 `google_artifact_registry_repository`。(d) `make deploy` 拆成两阶段 `deploy-infra` + `deploy-views`,反映"BQ sink 目标表要 GE toggle + 流量流过后才存在"这个事实。(e) `deploy_cloud_run` 默认改成 `false`,新手可以先本地跑。(f) README 加了完整的前置条件清单 + 5 个常见错误的排查章节。
- **2026-07-06** — Quota dashboard 下掉 `image_gen` / `video_gen` / `idea_gen`。GE 的图/视频/idea 生成跑在 Google 内部基础设施,不发 customer audit log,只能靠 prompt 关键词猜,把"总结一下这个视频"这种误判成生视频。tier_limit 配置留在 `quota_config` 里,以后 GE 出真的计数器再复活。
- **2026-07-06** — 配额总量现在按**已购 seats** (`licenseConfigs`) 算,不再按活跃用户数。之前买 20 seats 只有 10 人活跃,平台总配额被少算一半;现在正确显示 20× 每 tier 上限 (显式分配的 tier 保留,剩余 seats 按 `quota.default_tier` 填)。feature 卡片 label 从 "eligible" 改成 "seats"。
- **2026-07-06** — NotebookLM 配额计数只算用户主动的写操作 (`Create*`/`Update*`/`Delete*`/`BatchCreate*`/`Generate*`),不算 UI 打开 notebook 时后台自动发的 20 多个 `Get*`/`List*`/`BatchGet*` 调用。单用户日活次数现在跟感知一致。另外:席位数 (`licenseConfigs` API) 现在每 24h 自动刷 (FastAPI 后台任务,`LICENSE_REFRESH_INTERVAL_SEC` 可调),也可以手动 `POST /api/refresh/seats`。
- **2026-07-06** — Quota Deep Dive: 单用户表头可点排序 (邮箱 / tier / 每个 feature 的使用率)。
- **2026-07-03** — Playground 发现:NotebookLM / Deep Research / 图片视频下载 API 都被 workforce-identity 检查挡住,不是 IAM 层。SA 无论授啥 role 都过不了。详见 `playground/de-api-probe/notebooklm-sa-gate.md` 和 `playground/ge-generation-probe/FINDINGS.md`。
- **2026-07-03** — 合规清理:LICENSE 从 MIT 换 Apache 2.0,36 个源文件加许可 header,硬编码的 actor-email 前缀改成 `SIM_PREFIX` 环境变量 (默认 `sim-`),`playground/` 里的真实 project ID / 用户 email / workforce hash 全部脱敏。
- **2026-07-02** — README 中英版加封面截图。
- **2026-06-30** — Snapshot Scheduled Query 更新,补上 8 个新 `s_*` 表 (之前只轮替 15 个 view,新增的没刷)。
- **2026-06-29** — Quota 页面:席位数从 live `v1alpha/licenseConfigs` 拉 (真实 20 席 SEARCH_AND_ASSISTANT tier),替代之前的静态配置。tier 上限内联编辑 + 加州午夜重置已经在了。
- **2026-06-28** — Prompt 反向归因:把 StreamAssist prompt 关联到 Deep Research (AsyncAssist ±60s) 和自定义 agent (`page_type='agent'` 之后)。
- **2026-06-27** — Views 查询时透明改名 `vivo-sim-*` → `demo-*` (源数据不动);后续参数化为 `SIM_PREFIX`。
- **2026-06-25** — NotebookLM audit log 抓取:正确命名空间是 `notebooklm.v1main.*` (不是公开 doc 说的 `v1alpha`)。观察到 6 个 service: Notebook, Source, Note, Artifact, AudioOverview, Account。
- **2026-06-22** — 顶栏时间过滤 (24h / 7d / 30d / all)。

---

## License

Apache 2.0 — 见 [`LICENSE`](./LICENSE). Built by Claude Code (Opus). 欢迎贡献。
