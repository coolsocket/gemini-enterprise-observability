# 常见坑排查

> 症状 → 原因 → 修法。如果没找到你的症状,先看看 [Known Limitations](./KNOWN_LIMITATIONS.zh-CN.md) —— 很多时候是预期行为。


**`make views` 报 "N view(s) skipped — waiting for log-sink tables"**
新项目上正常。列出来那些表 (`cloudaudit_googleapis_com_*`, `discoveryengine_googleapis_com_*`) 只有 Logs Router sink 实际送过一条记录后,BQ 才会建。开好 GE toggle、发几条 chat、等 ~2 分钟,再跑 `make views` —— 计数会一路减到 0。

**`gcloud builds submit` 在 `gcr.io/...` 报 `NOT_FOUND`**
`gcr.io` (Container Registry) 2024 年 2 月被 Google 废弃,之后建的 project 都没有。本仓库已经迁到 Artifact Registry —— 确保你在最新 `main` 上,`IMAGE` 变量解析出 `<region>-docker.pkg.dev/...`。先跑 `make tf-apply` 让 Terraform 建 AR repo,再跑 `make image`。

**第二次 `terraform apply` 报 `Error 409: Already Exists`**
第一次 `tf-apply` 被中断了 (权限、quota、网络抖动、Ctrl-C),部分资源已经在 GCP 里创建但还没写进 terraform state。第二次 apply 想重新建 → 409。恢复:

```bash
make tf-import-orphans PROJECT=<你的项目> REGION=<region>
make tf-apply          PROJECT=<你的项目> REGION=<region>
```

`tf-import-orphans` 对每个可能泄漏的资源都跑 `terraform import` (dataset + 6 张 metadata 表、service account、log sink、Artifact Registry repo、audit config、已启用的 API,还有 Cloud Run 如果开了)。**幂等** —— "已在 state 里"和"不存在"都当 no-op,可以随便重跑。

**`make deploy-infra` 停在 "Continue anyway?" 或提示 audit-config 警告**
是 `make preflight` 在做它的活儿 —— 在 `terraform apply` 之前先扫一遍报告:
  1. `ge_observability` dataset / SA / sink / AR repo 里哪些已经存在 (需要 `tf-import-orphans` 或换个 `DATASET=` 名字)。
  2. 权威型的 `discoveryengine.googleapis.com` audit config 会不会被改 (它是唯一会覆盖的资源 —— 会清掉你原有的 `exempted_members`)。

脚本 / CI 里跳过交互式确认:
```bash
CONFIRM=y make deploy-infra PROJECT=<p> REGION=<r>
```

用不同的 dataset 名字 (推荐 —— 如果 `ge_observability` 是别的团队在用):
```bash
make deploy-infra PROJECT=<p> DATASET=ge_observability_v2 REGION=<r>
```

**Preflight 拒绝: "region mismatch, ALLOW_REGION_MISMATCH=y to bypass"**
你传的 `REGION` (比如 `asia-southeast1`) 跟 dataset 的 `BQ_LOCATION` (比如默认的 `US`) 不匹配。这**默认阻断**,因为大多数情况是你想统一 region 但只记住了一个变量。而且 BQ dataset location **建完不可改**,以后要修就得 `tf-destroy` + 重新灌数据。

修 —— 统一 region:
```bash
make deploy-infra PROJECT=<p> REGION=asia-southeast1 BQ_LOCATION=asia-southeast1
```
真的要数据合规 (数据在欧洲、计算在美国等)? 显式绕过:
```bash
ALLOW_REGION_MISMATCH=y make deploy-infra PROJECT=<p> …
```

**"我已经用混合 region 部署过了,怎么救?"**
Dataset location 原地改不了。两条路,看你累积多少有用数据:

*情况 A —— 新部署,数据还不多 (大多数人应该走这条)*:
```bash
# 1. 全推倒重来
cd terraform && terraform destroy \
    -var project_id=<p> -var region=<老region> \
    -var bq_location=<老location> -var dataset_id=<d> -var container_image=…
# (delete_contents_on_destroy=false 会拒绝 —— 这次救援临时覆盖)
# 或手动: bq rm -r -f <p>:<d>  &&  make tf-import-orphans + terraform state rm

# 2. 用正确 region 重新部署
make deploy-infra PROJECT=<p> REGION=asia-southeast1 BQ_LOCATION=asia-southeast1
```

*情况 B —— 生产 dataset 已经攒了几周日志要保留*:
```bash
# 1. 现有 dataset 导出到 GCS
bq extract --location=<老location> \
  '<p>:<d>.cloudaudit_googleapis_com_data_access' \
  gs://<backup-bucket>/data_access-*.avro
# (每张要保留的表都要跑一次)

# 2. destroy + 用新 region 重建 (同情况 A)

# 3. 从 GCS 灌回新 dataset
bq load --location=<新location> --source_format=AVRO \
  '<p>:<d>.cloudaudit_googleapis_com_data_access' \
  gs://<backup-bucket>/data_access-*.avro
```
实操里, 如果只是 dashboard 用途, 情况 A 几乎总是可以 —— dashboard 展示的都是近实时数据, 老审计日志几周后基本不查了。

**BigQuery 数据合规: dataset 放到特定 region (比如新加坡)**
传 `BQ_LOCATION=asia-southeast1` (或 `europe-west1`, `asia-east1` 等):
```bash
make deploy-infra PROJECT=<p> REGION=asia-southeast1 BQ_LOCATION=asia-southeast1
```
`REGION` (Cloud Run + Artifact Registry) 和 `BQ_LOCATION` (BQ dataset) 是**独立的** —— 你可以把 dashboard 放 `us-central1`,但分析数据留在新加坡。dataset location 建完不可改;要迁需要 `tf-destroy` + 重 apply (数据保留因为 `delete_contents_on_destroy = false`,但要重新灌进新 dataset)。

**Cloud Run URL 返回 403**
把调用方加到 `terraform.tfvars` 的 `iap_invokers` 里再 apply。没走 IAP 用 `roles/run.invoker`,走了 IAP 用 `principal://` 格式。还是 403 就看看 Cloud Run 是否要求 auth。

**`make views` 报 `Not found: Table quota_config`**
`make bootstrap` 跳了。那步创建 view 引用的 metadata 表 (`terraform apply` 也会幂等地建 —— 如果 apply 成功后还看到这个错,检查 `PROJECT` 和 `DATASET` 两边一致)。

**运行时 API 返回 BigQuery 查询 403**
runtime SA (`ge-observability-sa@…`) 要在 project 上有 `roles/bigquery.jobUser`,dataset 上有 `roles/bigquery.dataViewer`。Terraform 都授了 —— 如果你在 Terraform 外重命名了 dataset,重新 apply 让 IAM 跟上。

**`bootstrap.py` 报 `licenseConfigs` 404 或 403**
你的 GE 部署可能还没 `licenseConfigs` API 响应 (非常新的 tenant),或调用方缺 `roles/discoveryengine.viewer`。脚本会优雅降级 —— Quota 页面的 seat 数会 fallback 到 `quota_config` 表里已经存的值。

---

