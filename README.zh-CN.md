# GE Observability

> **语言**: 中文 · [English](./README.md)

[![在 Cloud Shell 中打开](https://gstatic.com/cloudssh/images/open-btn.svg)](https://shell.cloud.google.com/cloudshell/editor?cloudshell_git_repo=https%3A%2F%2Fgithub.com%2Fcoolsocket%2Fgemini-enterprise-observability&cloudshell_git_branch=main&cloudshell_workspace=.&cloudshell_tutorial=docs%2FTUTORIAL.zh-CN.md&show=ide%2Cterminal)

**推荐安装路径** —— 点上面按钮。Cloud Shell 会:
- 自动用你 Google 账号 auth
- 预 clone 好仓库到编辑器里
- **右边弹出一个交互式教程面板**,一步步引导:选 project → 一键开 API → wizard → deploy → backfill → serve
- 预装好 `gcloud` / `terraform` / `python3` / `npm`

跟着右边教程面板走,大约 30 分钟。如果你更想在自己本机手工跑:

```bash
make install         # venv + npm 依赖 + 复制 .env.example → .env + doctor 报告
make wizard          # 交互式问 project ID / region 等,写 .env
make deploy-infra    # provision + build + bootstrap  (需要项目 Owner —— 详见 DEPLOYMENT.zh-CN.md)
```

本地装也行 (见下面 [快速开始](#快速开始)),但你得自己在本机装好那套工具 + auth。

![总览页 — 中文](./docs/screenshots/overview-zh.png)

**Gemini Enterprise** 的自托管仪表盘 —— 采用度、治理、审计。Cloud Logging → BigQuery → React + FastAPI。

回答的问题:
- 谁是 **POWER_USER / ACTIVE_CONSUMER / TRIAL / LURKER**?
- 谁建了哪个 **agent / engine / data store**?
- 用户问了什么 **prompt**,模型怎么答的?
- 哪个 **engine** 最受欢迎?
- 哪些 **seat** 占了但没用?
- **Deep Research / NotebookLM / 自建 agent** 各调用了多少次,谁调的,具体哪几次?

## 文档

- **[部署指南](./docs/DEPLOYMENT.zh-CN.md)** —— 前置条件、两阶段部署、验证清单、分步 debug
- **[常见坑排查](./docs/TROUBLESHOOTING.zh-CN.md)** —— 症状 → 原因 → 修法
- **[已知限制](./docs/KNOWN_LIMITATIONS.zh-CN.md)** —— 20 项,按数据 / API / 部署 / 运维 4 类分组
- **[变更日志](./CHANGELOG.zh-CN.md)** —— 用户可见变化,最新在上
- **[不变量](./infra/contexts/deploy/INVARIANTS.md)** —— 部署时的不变量 (每个修复所依赖的前置条件)
- **[GE 控制台配置](./docs/GE_CONSOLE_SETUP.md)** —— 唯一剩下的手工 GE toggle (`Enable Feedback`)
- **[运维手册](./docs/RUNBOOK.md)** —— 刷新、轮换、backfill 剧本

---

## 页面

| 页面 | 内容 |
|---|---|
| **总览** | DAU 趋势 · persona 分布饼图 · KPI 卡片 · engine 列表 · 数据新鲜度 |
| **用户选择** | 可搜索/排序目录:每用户 × 每个 feature 的活动 |
| **用户深挖** | 单用户全维度,drill 到底层 audit 事件 |
| **Agent 看板** | 每 agent 汇总 (Deep Research / NotebookLM / 自定义),用户分布,事件时间线 |
| **对话内容** | Prompt + 响应气泡,`matched / prompt-only` 过滤 |
| **数据访问** | 按 method 分桶,含 NotebookLM / A2A / Deep Research 列 |
| **文件 & Agents** | 会话文件活动 + 自定义 agent 导航 |
| **Builder 榜** | 谁建 / 更新 / 删了哪些资源 |
| **管理操作时间线** | Path 3 审计日志时间线 |
| **Quota** | 每 feature 使用量 vs 已购 seats, tier 配置, seat 库存 |
| **Settings** | Snapshot 刷新状态 + 数据源配置 |

---

## 快速开始

```bash
git clone https://github.com/coolsocket/gemini-enterprise-observability
cd gemini-enterprise-observability

# 一次性 setup: venv + npm 依赖 + .env 模板 + 健康检查
make install

# 填你的 GCP 项目 ID 等
$EDITOR .env

# 认证 (Python + Terraform)
gcloud auth application-default login

# 本地预览 (BQ dataset 必须已存在 —— 详见完整部署指南)
make serve
open http://127.0.0.1:8000
```

新 GCP 项目还没建 dashboard 的 BQ dataset / sink:

```bash
make deploy-infra          # provision + build + bootstrap
# (手动: GE Console 开一个 toggle,发点流量)
make deploy-views          # 日志流过来之后 apply 分析视图
```

完整流程 + 验证清单: **[docs/DEPLOYMENT.zh-CN.md](./docs/DEPLOYMENT.zh-CN.md)**。

卡住了? 试 **`make doctor`** (非破坏性环境检查) 或看 **[常见坑排查](./docs/TROUBLESHOOTING.zh-CN.md)**。

---

## 架构

```
GE 用户操作 (UI + REST)
        ↓ 日志
Cloud Logging (audit + gen_ai + user_activity)
        ↓ Logs Router sink
BigQuery dataset: ge_observability
   • sink 原始表
   • ~21 个分析 view (v_*)
   • materialized 快照 (s_*, 6h 刷)
   • quota_config + engine_metadata + …
        ↓ google-cloud-bigquery
FastAPI on Cloud Run (or 本地)
        ↓ fetch
React 18 + Vite + Tailwind (中 / EN i18n)
```

完整 log-name 清单、表名、view→snapshot 映射见 **[docs/DEPLOYMENT.zh-CN.md § 架构细节](./docs/DEPLOYMENT.zh-CN.md)**。

---

## 本地开发

两端 HMR:

```bash
make api-run                       # FastAPI @ http://127.0.0.1:8000 (--reload)
cd apps/web && npm run dev         # Vite @ http://127.0.0.1:5173 (代理 /api → :8000)
```

或者单进程预览 (前端已 build,FastAPI 直接 serve):

```bash
make serve PORT=8011
ssh -L 8011:127.0.0.1:8011 <远端机器>   # 远程跑就开隧道
open http://localhost:8011
```

测试:

```bash
.venv/bin/pytest tests/unit/         # 25 条静态断言 (无需 BQ)
```

---

## 仓库结构

按 bounded-context 分层 (2026-07-06 TDDD 重构后):

```
ge-observability-service/
├── apps/api/                             # FastAPI 后端,DDD-ish 分层
│   ├── main.py                           # ~50 行:装 router + 启动
│   ├── shared/
│   │   ├── common.py                     # 跨切:_json_safe, valid origins
│   │   └── infrastructure/bq_client.py   # THE bigquery.Client 单例 + 配置
│   ├── routes/                           # 按 context 分的 HTTP 薄层
│   │   ├── meta.py    observability.py   quota.py   refresh.py   spa.py
│   └── contexts/                         # 每 context 的 domain (纯逻辑无 I/O)
│       ├── observability/
│       │   ├── INVARIANTS.md             # INV-obs-001 (snapshot fallback), INV-obs-002 (refresh precheck)
│       │   └── domain/
│       │       ├── view_registry.py      # VIEWS + VIEWS_WITH_* + snapshot_name
│       │       └── query_builder.py      # QuerySpec, build_query_spec, render_sql
│       └── quota/
│           ├── INVARIANTS.md             # INV-quota-001 (seats = licenseConfigs.total)
│           └── domain/
│               ├── license_parse.py      # 纯函数: parse_license_configs(api_json)
│               └── tier_allocation.py    # 纯函数: allocate_seats(purchased, assigned, default)
├── apps/web/src/                         # React 18 + Vite + Tailwind
├── infra/
│   ├── sql_templates/views.sql.tmpl      # 21 个 BQ view
│   └── contexts/deploy/
│       ├── INVARIANTS.md                 # INV-001 (BQ_LOCATION 跟随 REGION)
│       └── application/                  # doctor / preflight / bootstrap / apply_views / import_orphans
├── terraform/                            # dataset + sink + IAM + AR + Cloud Run
├── docs/                                 # DEPLOYMENT / TROUBLESHOOTING / KNOWN_LIMITATIONS / GE_CONSOLE_SETUP / RUNBOOK
├── tests/unit/                           # 25 个回归断言
├── playground/                           # audit-log 逆向笔记
├── CHANGELOG.md
├── Makefile                              # install / doctor / serve / deploy-* / resume
├── pyproject.toml                        # Python ≥ 3.9
└── LICENSE                               # Apache 2.0
```

---

## 核心贡献者

- [**@panliuyang-debug**](https://github.com/panliuyang-debug) —— 从零 GCP project 部署,提了 issue [#1](https://github.com/coolsocket/gemini-enterprise-observability/issues/1),对 audit log 做了深入的追踪调查。两个改变产品行为的发现:`Engine.observabilityConfig` 是真实存在的 API 字段 (GE Console 不再需要手动点),`jsonPayload.serviceTextReply` 里带着 UI 聊天的完整响应文本 (dashboard 配对率从 ~10% 提到 ~60%)。此外报了 5 个 Cloud Run / terraform / SQL 相关 bug —— 全部在 [`a5a3d3f`](https://github.com/coolsocket/gemini-enterprise-observability/commit/a5a3d3f) 修复。

欢迎贡献 —— issue、PR、audit log 排查经验都欢迎。

---

## License

Apache 2.0 —— 见 [`LICENSE`](./LICENSE). Built by Claude Code (Opus)。
