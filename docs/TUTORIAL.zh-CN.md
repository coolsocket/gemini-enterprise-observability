<!--
  Cloud Shell 交互式教程 · GE Observability
  README 里"在 Cloud Shell 中打开"按钮指向这个文件。Cloud Shell 解析
  <walkthrough-*> HTML 标签,渲染成交互步骤面板(project 选择器 widget、
  一键 enable APIs 按钮等),放在终端旁边。

  本地预览:在 Cloud Shell 里跑 `teachme docs/TUTORIAL.zh-CN.md`
-->

# GE Observability · 部署到你自己的项目

## 欢迎

大概 30 分钟,你会从一个全新 GCP 项目一路走到**装满真实数据的 GE
观测板**。你的 gcloud 认证已经在这个 Cloud Shell 里了,每一步都跑在
**你自己的项目、你自己的数据**上。

你会:
1. 选(或新建)GCP 项目 + 打开需要的 API
2. 交互式 wizard 生成 `.env`
3. terraform 部署 sink + BigQuery + service account
4. 在 GE Admin Console 打开 audit / P&R Logging(一次性手工步骤)
5. 应用视图 + backfill 过去 30 天历史
6. 本地起 dashboard

**你项目里必须已有**(这个教程不会帮你搞这些):
- 已启用计费
- 已经跑起来一个 Gemini Enterprise engine
- 你有 Owner 或 [DEPLOYMENT 里列的复合角色](./DEPLOYMENT.zh-CN.md)。
  Backfill(第 7 步)还需要 `roles/logging.privateLogViewer` 才能读
  `_Default` bucket 里的 audit 日志。

点右下角 **Start** 开始 →

## 选一个项目

选那个装着你 GE engine 的 GCP 项目。下面这个 widget 会确认计费已启用,
并把它设为后续教程的默认 `gcloud` 项目。

<walkthrough-project-setup billing="true"></walkthrough-project-setup>

当前目标:<walkthrough-project-id/>

## 一键打开所需 API

点下面按钮,把整套部署要用的 API 都一次开好:

<walkthrough-enable-apis apis="bigquery.googleapis.com,logging.googleapis.com,run.googleapis.com,cloudbuild.googleapis.com,artifactregistry.googleapis.com,discoveryengine.googleapis.com,iam.googleapis.com,iamcredentials.googleapis.com,bigquerydatatransfer.googleapis.com,serviceusage.googleapis.com">
</walkthrough-enable-apis>

## 配置

Wizard 生成一份 `.env` 文件,里面写着你的 BQ 项目、region、dataset:

```bash
make wizard
```

一般接受默认值就行 —— 唯一值得注意的是 **region**,建议选离你最近的
(东亚用 `asia-southeast1`,欧洲用 `europe-west1`)。

验证:

```bash
cat .env
```

## 部署基础设施

一次搞定:BigQuery dataset、Log Router sink、service account、IAM
授权、Artifact Registry、metadata 表。顺便 seed 一份默认 quota 限额
(所有值都能在 /quota 页面在线改)。

```bash
make deploy-infra PROJECT=<walkthrough-project-id/>
```

会看到 terraform 输出、Cloud Build 打包镜像、`bootstrap` 同步你的
GE engine metadata 到 BQ。**大概 3-5 分钟。**

**期望结果**:`terraform apply` 报告类似 "5 resources added, 0 changed,
0 destroyed",没有未处理错误。

## GE Admin Console 里手动打开日志(一次性)

**这一步 Google GE Console 独占,暂时没有 CLI 等价物**。对每个你想
观测的 engine,打开:

<walkthrough-editor-open-file filePath="docs/GE_CONSOLE_SETUP.md">docs/GE_CONSOLE_SETUP.md</walkthrough-editor-open-file>

跟着 "Enable audit logs + prompt & response logging" 那节做。具体是:

1. GE Admin Console → 你的 engine → **Settings** → **Observability**
2. **Data Access audit logs** 打开
3. **Prompt & Response Logging** 打开
4. **OpenTelemetry Instrumentation** 打开

第 3 项不开,"Conversations" 页永远是空的(chat prompt/response 不会
进 BigQuery)。

## 产生一些流量 + 等等

登进你的 GE tenant,做几件事:
- 问 chat 几个问题
- 起一个 Deep Research 任务
- 打开 NotebookLM,创建一个 notebook
- 上传 session 文件(如果你的用法涉及)

然后**等 2-5 分钟**,让日志从 GE → Cloud Logging → BQ sink 目标表流完。

## 应用视图 + backfill 历史

sink 目标表已经在了,应用 21 个分析视图 + `canonical_actor` UDF:

```bash
make deploy-views PROJECT=<walkthrough-project-id/>
```

然后从 Cloud Logging 捞过去 30 天的历史(受你 `_Default` bucket
保留期限制 —— 脚本会打印实际覆盖多少天):

```bash
make backfill PROJECT=<walkthrough-project-id/> DAYS=30
```

两条命令都幂等,重跑无副作用。

## 启动 dashboard

```bash
make serve PROJECT=<walkthrough-project-id/>
```

会看到 uvicorn 在 8000 端口起来。点 Cloud Shell 右上角 "Web Preview"
按钮,port 8000。

**你应该能看到:**
- **Overview**:总人数 / active_consumers / chat_turns
- **Persona**:用户按 POWER_USER / ACTIVE_CONSUMER / TRIAL 分类
- **Data Access**:每个用户按 feature 的 API 调用明细
- **User Deep Dive**:点任意用户 → identity badge(Google / OIDC / SA)
  + 各 engine 使用拆分
- **Quota**:各 tier 限额(可在线编辑)

## 完事了

之后运维:
- **拉了新代码后**:`make hotfix PROJECT=<walkthrough-project-id/>`
  (应用最新 view SQL + 触发 snapshot refresh,一条命令)
- **部到 Cloud Run**(团队共用 dashboard):改
  `terraform/terraform.tfvars` 设 `deploy_cloud_run = true` + 加
  invokers,然后 `make tf-apply`
- **运维手册 + 故障排查**:
  <walkthrough-editor-open-file filePath="docs/RUNBOOK.md">docs/RUNBOOK.md</walkthrough-editor-open-file>
  和
  <walkthrough-editor-open-file filePath="docs/TROUBLESHOOTING.zh-CN.md">docs/TROUBLESHOOTING.zh-CN.md</walkthrough-editor-open-file>

<walkthrough-conclusion-trophy></walkthrough-conclusion-trophy>
