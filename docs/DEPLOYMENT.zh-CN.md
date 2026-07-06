# 部署指南

> 完整版。5 行速通看主 [README](../README.zh-CN.md)。


## 前置条件

开始之前请确认以下都到位:

**本地工具在 `PATH` 里**
- `gcloud` (Cloud SDK ≥ 460)
- `terraform` ≥ 1.5
- `python3` ≥ 3.11 + `pip`
- `npm` ≥ 8 (只有想改前端时需要;容器构建自己会装)
- `make`

**GCP 项目状态**
- 项目已建、billing 已开 (`gcloud beta billing projects link ...`)
- **Gemini Enterprise engine 已在目标项目里**(本仓库只观察,不建 GE)
- **Cloud Build API 预先启用** 好让 `make image` 第一次就通:`gcloud services enable cloudbuild.googleapis.com --project=<project>` (Terraform 会启,但顺序不对时先被这个卡)

**deploying principal 需要的 IAM role — 2026-07-06 一个个撞出来验证过:**

| Terraform 资源 | 最小权限 (具体) | 覆盖的 composite role |
|---|---|---|
| Enable required APIs | `serviceusage.services.enable` | `roles/serviceusage.serviceUsageAdmin` |
| 建 BQ dataset + tables | `bigquery.datasets.create` / `tables.create` | `roles/bigquery.dataOwner` |
| 建 Log Router sink | `logging.sinks.create` + `logging.buckets.get` | `roles/logging.configWriter` |
| 建 Artifact Registry repo | `artifactregistry.repositories.create` | `roles/artifactregistry.admin` |
| 建 runtime service account | `iam.serviceAccounts.create` | `roles/iam.serviceAccountAdmin` |
| 给 SA 授 project-level role (bigquery.jobUser, discoveryengine.viewer) | `resourcemanager.projects.setIamPolicy` | `roles/resourcemanager.projectIamAdmin` |
| 设 discoveryengine 的 audit-config (authoritative) | `resourcemanager.projects.setIamPolicy` (同上) | `roles/resourcemanager.projectIamAdmin` |
| 建 Cloud Run service (`deploy_cloud_run = true` 时) | `run.services.create` | `roles/run.admin` |

**最简单答案:项目 `roles/owner`。** 组织不让给 Owner 就把上面 7 个 composite 都授给部署方。缺任何一个 `terraform apply` 会在中途 403,需要 [`make tf-import-orphans`](../TROUBLESHOOTING.zh-CN.md) 恢复。

**认证 (两个都要)**
- `gcloud auth login` —— Terraform + Cloud Build CLI 用
- `gcloud auth application-default login` —— Python 脚本 (`apply_views.py`, `bootstrap.py`) 和 FastAPI 后端都走 ADC

## 完整端到端验证清单

`terraform apply` 跑完不等于部署完成 —— 有几步依赖你**手动**去 GE 控制台开 toggle,还有几步要等 Logs Router 真的把日志送过来。照这个清单一项项打勾,才算真正 green:

- [ ] `make deploy-infra PROJECT=<p> REGION=<r>` 退出码 0
  - 建 24 个资源 (BQ dataset、sink、6 张 metadata 表、IAM、audit-config、Artifact Registry 仓库、service account)
  - build + push 镜像到 Artifact Registry
  - `bootstrap.py` 装 `engine_metadata` / `datastore_metadata` / `resources_alive`,seed `quota_config` (含真实 seat 数)
- [ ] Terraform 的 `dataset_full_name` 输出打印你的 project 和 dataset
- [ ] `bq ls <project>:<dataset>` 能看到 6 张 metadata 表
- [ ] 打开每个 engine 的 **GE Admin 控制台**,翻开 toggle:
  - [ ] OpenTelemetry Instrumentation (生成 `trace_id`,用来配对 prompt+response)
  - [ ] Prompt & Response Logging (写 `gen_ai.user.message` + `gen_ai.choice`)
  - [ ] Feedback (可选;开了才能捕获点赞点踩)
  - 带截图的完整步骤:`docs/GE_CONSOLE_SETUP.md`
- [ ] 产生真实 GE 流量 —— 至少:每个 engine 一条 chat,一次 Deep Research 提交,一次 NotebookLM 交互
- [ ] 等 ~2-5 分钟让 Logs Router 送第一批日志。确认:
  ```bash
  bq ls -a <project>:<dataset> | grep -E 'cloudaudit_|discoveryengine_'
  ```
  应该能看到 `cloudaudit_googleapis_com_activity`、`cloudaudit_googleapis_com_data_access`,以及 (chat/DR 触发过后) `discoveryengine_googleapis_com_gemini_enterprise_user_activity` 和 `..._gen_ai_choice`。缺哪个继续发对应类型的流量 —— BQ 在第一条匹配日志落下时才自动建表。
- [ ] `make deploy-views PROJECT=<p>` —— 现在应该 **全 green**:`applied 21/21 views`,零 waiting / cascade / real error。如果还有 waiting,对应的 audit log 表还没收到第一条,继续发对应流量再重跑即可。
- [ ] `make serve PROJECT=<p>`,浏览器开 `http://127.0.0.1:8000` —— 每个页面都点一遍:Overview、Users、User Deep Dive、Agents、Engines、Conversations、Data Access、Quota、Settings。不应该有"一直 loading"或 500。
- [ ] Quota 页面 "Seats" 面板显示非零 `license.total_seats` (从 `licenseConfigs` 实时拉)
- [ ] 想上 Cloud Run: `terraform.tfvars` 里设 `deploy_cloud_run = true` + 加 `iap_invokers = […]` + `make tf-apply` 再跑一次,然后 `gcloud run services proxy ge-observability --port 8080 --region <r>`

上面任何一项超过几分钟还是红,下面的 Troubleshooting 章节列了最常见的原因。

## 两阶段部署 (新项目推荐)

```bash
git clone https://github.com/coolsocket/gemini-enterprise-observability
cd gemini-enterprise-observability

# ---------- 阶段 A: 基础设施 + 镜像 + metadata ----------
make deploy-infra PROJECT=my-project REGION=us-central1
# 跑: terraform apply → gcloud builds submit → bootstrap.py
#
# `REGION` 控制什么 (默认 us-central1):
#   • Artifact Registry 仓库位置 (镜像存哪)
#   • Cloud Run 服务位置 (如果 deploy_cloud_run=true, dashboard 跑在哪)
# `BQ_LOCATION` 控制什么 (默认 US, 独立变量):
#   • BigQuery dataset 位置 —— 新加坡设 asia-southeast1、比利时设
#     europe-west1、或者 US / EU / asia 这种 multi-region。
#     数据合规常见选: BQ_LOCATION=asia-southeast1 把分析数据留在新加坡。
# Log Router sink 是 global。REGION 和 BQ_LOCATION 都是一锤子买卖,原地
# 改不了 —— 要迁 region 就 tf-destroy + 重 apply。

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

## 预览 dashboard

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

## 一键 view 恢复: `make resume`

view 建失败后重试的 90% 场景:

```bash
# 想要上游修复自己 pull (Make 不会替你做):
git pull

# 然后一条命令:
make resume PROJECT=responsive-lens-421108 DATASET=ge_observability
```

`make resume` 内部做:
1. 通过 `bq show` 查现有 dataset 的**真实 `BQ_LOCATION`** —— 这样 preflight 的 region-mismatch gate 不会误伤已经在 GCP 上的现状
2. 跑 `apply_views.py`,幂等:21 个 `CREATE OR REPLACE VIEW` 无变化就 no-op,有 schema-drift / 依赖 fix 时精准重建受影响的那几个

耗时: ~30-60 秒。**不动 git / Terraform / 镜像 / bootstrap** —— 那些都你自己控制。

## 失败后恢复 (幂等性一览)

所有部署步骤都幂等 —— 不会删数据。有的智能跳过,有的每次都重跑。参考此表决定重试哪一步,不用整链重跑:

| 步骤 | 智能跳过? | 重跑代价 | 说明 |
|---|---|---|---|
| `preflight`             | n/a  | ~5 秒  | 只读扫描,不改任何东西 |
| `tf-apply`              | ✅ **完全智能** | ~10-30 秒 | Terraform diff state,已存在且一致的资源 no-op |
| `image`                 | ❌ **总是重 build** | 1-3 分钟 | `gcloud builds submit --tag=:latest` 不 hash 源码,每次全量 build。**知道镜像没变时用 `SKIP_IMAGE=true`** (比如只改了 Terraform) |
| `bootstrap`             | 大部分 | ~5 秒 | metadata 表 TRUNCATE-load (量小);`observabilityConfig` PATCH 幂等;`quota_config` MERGE 只动变了的行 |
| `views` / `deploy-views` | 半智能 | 30-60 秒 | 每个 `CREATE OR REPLACE VIEW` 都执行,但重建相同定义的 view 等于 no-op |

**常见恢复场景:**

```bash
# views 挂了 (schema drift / 等日志),其他都好:
make deploy-views PROJECT=<p>

# 只有 tf-apply 有改动,image / bootstrap / views 都还好:
make tf-apply PROJECT=<p>

# 想整链重跑,但跳过慢的 image build:
SKIP_IMAGE=true make deploy-infra PROJECT=<p>

# GE console 里加了新 engine,只想重新拉 metadata:
make bootstrap PROJECT=<p>
```

## 分步走 (debug)

```bash
make tf-plan   PROJECT=my-project    # 预览
make tf-apply  PROJECT=my-project    # 建基础设施 + Artifact Registry repo
make image     PROJECT=my-project    # build + push 镜像到 AR
make bootstrap PROJECT=my-project    # seed metadata
# (手动开 GE 控制台 toggle + 跑一点流量)
make views     PROJECT=my-project    # apply BQ view (重跑直到全部通过)
```


