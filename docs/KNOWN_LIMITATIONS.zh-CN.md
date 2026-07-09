# 已知限制

> 分成 4 类,debug 时快速定位。演变历史见 [CHANGELOG](../CHANGELOG.zh-CN.md)。


Dashboard 展示的所有信号都来自 GE 真正 emit 的东西。下面是**看不到**或**做不到**的,按类别分好方便查:

### 数据 — GE 不 emit 的信号

1. **Chat prompt ↔ response 配对** (2026-07-06 基本解决)。两条路径:(a) `v1alpha` REST 聊天走 `gen_ai.choice` 配对 (`trace_id`,含 reasoning + finish_reason);(b) UI (`v1main`) 不写 `gen_ai.choice`,但只要 `sensitiveLoggingEnabled=true` (bootstrap 自动开),模型响应文本会内嵌在同一行 `user_activity` 的 `jsonPayload.serviceTextReply` 里。`v_conversations_with_response` `COALESCE` 两条路径。实测配对率从 ~10% 提到 ~60%。剩余 `no_response` 通常是 Deep Research 响应 (见下) 或错误。

2. **Deep Research prompt + response 内容,以及计数可信度**。DR 响应本身不 emit 到 Cloud Logging —— 看内容还是要去 GE 后台 Deep Research 任务列表。**关于计数**: `AssistantService.AsyncAssist` 是我们对"一次 DR 提交"的代理,但 GE (2026-07) 在普通聊天时也会同时触发 AsyncAssist —— 一条"帮我查一下深圳的天气"的 prompt 在同一秒触发了 `StreamAssist` 和 `AsyncAssist` + `ReadAsyncAssist` (线上审计日志验证过)。`resourceName` 两种场景都是 `.../assistants/default_assistant`,无法区分。现在的做法:候选 prompt 已经跟正常聊天响应配对时不再归因给 DR —— 但 AsyncAssist 总数本身可能虚高。桶名保留 `deep_research` 兼容前端,hint 里加了提示。

3. **图片 / 视频 / idea 生成**。GE 后端跑在 Google 内部,不发 customer audit log。2026-07-06 从 Quota dashboard 下掉了 —— 之前的 prompt 关键词启发式会把"总结一下这个视频"这种误分类。`quota_config` 里的 `tier_limit` 配置保留,以后 GE 出真计数器再复活。

4. **多模态上传**。`streamAssist` 不接受 `inlineData`,图片/文件走单独 session-file 流程。Dashboard 展示 `session_files` 计数,但看不到内容。

5. **内置 agent 跟 chat 区分不开**。Idea Generation / Co-Scientist / AlphaEvolve 全部走 `AssistantService.StreamAssist`。agent 引用在 request body 里 —— 要拆开得开 DATA_WRITE audit log + payload capture (默认关)。

6. **Custom agent 调用只能看导航不知调用**。点开 detail 页时 `UserEventService.WriteUserEvent` 带 `agentinfo.{agentid,name}` (Agents 页展示的 nav events),但实际调用要么走 StreamAssist (跟 chat 混),要么走 A2A (在 `a2a_invocations` 里)。

7. **A2A 无 per-agent 细分**。A2A 调用总量在 `a2a_invocations`,还没按目标 agent 拆分。

8. **CreateAgent 缺新 agent 的 resource ID**。audit log `resourceName` 是 parent (`assistants/default_assistant`) 不是新 agent ID。所以"哪个 user 建了哪些 alive 资源"没法追溯。总览页 fallback 用 `ListAgents` API 查全系统 alive 数。

### API — service account 做不了的事

9. **NotebookLM API 对 SA 完全封锁**。就算 custom role 授全 `discoveryengine.notebooks.*` 权限,SA 调用还是 `403 "The caller does not have permission"`。gate 在 NotebookLM 服务层 (workforce identity + Regional Access Boundary registry),不在 IAM 层。试图绑 role 时会看到 `Regional Access Boundary HTTP request failed... Account not found for email: <hash>|<user>` warning —— 只是提示 (绑定实际成功),表明底层 gate 存在。完整证据见 [`playground/de-api-probe/notebooklm-sa-gate.md`](../playground/de-api-probe/notebooklm-sa-gate.md)。

10. **Deep Research REST API 对 SA 封锁**。`AsyncAssist` 在公开的 `v1alpha` Discovery Engine schema 里根本没有 —— 是 UI 内部 (`v1main`) 的 method,同一个 workforce-identity gate。SA 不能程序化提交 DR。真人在 UI 里发起的 DR 我们**能**从 audit log 看到,只是没法从代码生成。

11. **生成的文件无法通过 API 下载**。`StreamAssist` 可以正常生成图 (Nano Banana 2) 或视频,并在流式响应里返回 `fileId`,但下载端点 (`sessions/{sid}:listFiles`, `:getFile`, `:downloadFile`) 全部返回 `403 "Session is not owned by the provided user"` —— 同一个 workforce gate。文件只能在 GE UI 里看。完整证据见 [`playground/ge-generation-probe/FINDINGS.md`](../playground/ge-generation-probe/FINDINGS.md)。

12. **Deep Research vs Search vs grounded-answer 是三个独立 service**。DR = `AssistantService.AsyncAssist`,Search API = `SearchService.Search`,grounded-answer = `ConversationalSearchService.GetAnswer`。我们的计数器分开桶,DR 永远不会跟 Search 混。

### 部署 — 自动化外的手工步骤

13. **GE engine 必须预先建好**。本仓库观察一个已有的 GE 部署,不建。先去 GE Admin Console 建 engine。

14. **GE Console toggle 大部分已自动化** (2026-07-06)。`bootstrap.py` 现在通过 Discovery Engine API `PATCH` 每个 engine 的 `observabilityConfig` 字段 —— `observabilityEnabled` (OpenTelemetry) + `sensitiveLoggingEnabled` (Prompt & Response Logging) 自动开。**只有"Enable Feedback"**还要手工去 GE Admin Console 点。要跳过自动化: `SKIP_OBSERVABILITY=true make bootstrap`。见 [`docs/GE_CONSOLE_SETUP.md`](./GE_CONSOLE_SETUP.md)。

15. **Sink 目标表是懒创建的**。`cloudaudit_googleapis_com_data_access` 和 `discoveryengine_googleapis_com_*` 只在第一条匹配日志真到达 sink 的时候才被 BigQuery 自动建。`make deploy-views` 会报哪些还在等,而且**幂等** —— 流量流过之后重跑即可。

16. **Cloud Run 访问需要手工配 IAP**。默认 `deploy_cloud_run = false`。改成 true 会建服务,但你还得在 `terraform.tfvars` 里加 `iap_invokers = […]`,以及 (通常) 配 Identity-Aware Proxy 才能外部访问。

### 运维 — 新鲜度 + 性能

17. **Snapshot 刷新周期 6 小时**。Dashboard 页面读的 `s_*` 快照表由 BigQuery Scheduled Query 每 6 小时刷。手动刷:`POST /api/refresh` (Settings 页有按钮)。live `v_*` view 永远是最新的但更慢。

18. **Seat 数刷新周期 24 小时**。`licenseConfigs` 在 API 启动时 + 每 24 小时被后台 asyncio 任务拉一次。手动刷:`POST /api/refresh/seats`。Cloud Run 冷启动触发新一次拉取;长期运行的进程一天准一次。

19. **PII 脱敏只有正则**。`v_conversations` 脱敏 email / 电话 / ID 数字 / 信用卡数字。**不是完整 DLP** —— 人名、地址、长文本 PII 都会透过来。生产上再叠一层 Cloud DLP。

20. **`quota_config.default_tier` 决定 seat-to-tier 分配**。总配额 = `Σ 各 tier (tier 的 seats × 该 tier 的 per-feature 上限)`。`user_tier` 表里显式分配过的用户按其分配算;剩余未分配的 seats 按 `quota.default_tier` (默认 `plus`) 填。Quota 页面 tier 配置编辑器里可改默认。


