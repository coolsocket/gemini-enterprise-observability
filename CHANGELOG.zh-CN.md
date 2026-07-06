# 变更日志


用户可见行为、配额语义、dashboard 数据模型变化时请更新此列表。最新在上。完整详情看 `git log`。

- **2026-07-06** — 修 [issue #1](https://github.com/coolsocket/gemini-enterprise-observability/issues/1) (panliuyang-debug 提的 fresh project 部署 8 点踩坑): (a) `google_cloud_run_v2_service` 里删掉 `PORT` env var —— Cloud Run 自动注入,provider v6 起显式设置会被拒绝; (b) Cloud Run 资源加 `deletion_protection = false`,避免首次部署失败之后需要 `terraform state rm` 才能恢复; (c) Cloud Run `depends_on` 加了 `google_artifact_registry_repository.dashboard`,顺序正确; (d) `bootstrap.py` 现在通过 Discovery Engine API `PATCH` 每个 engine 的 `observabilityConfig` (`observabilityEnabled` + `sensitiveLoggingEnabled`) —— **不再需要去 GE Admin Console 点击**了 (只有 "Enable Feedback" 仍需手工)。`SKIP_OBSERVABILITY=true` 可跳过; (e) **配对大改善**: `v_conversations_with_response` 现在 `COALESCE` `gen_ai.choice` (trace-JOIN) 和 `user_activity.jsonPayload.serviceTextReply` —— 纯 UI 对话的配对率从 ~10% 提到 ~60%。新 `join_status` 值:`matched_gen_ai_choice` / `matched_service_reply` / `no_response`; (f) DR 归因诚实度: 报告人证明了普通聊天会触发 AsyncAssist (跟 StreamAssist 同时发,审计日志逐字节一致,`resourceName` 也没区别) —— `v_deep_research_prompts` 现在会跳过已经跟正常聊天配对的 prompt,Quota 的 DR feature hint 加了不精确警告。`docs/GE_CONSOLE_SETUP.md` 反映新的 API 自动化。
- **2026-07-06** — `已知数据边界` 章节重整成 `已知限制`,20 条按四类分组:数据(GE 不 emit 的信号)、API(SA 做不了的事)、部署(自动化外的手工步骤)、运维(新鲜度/PII/tier 分配)。全部条目更新,删掉一条过时的"没有 seat API"(现在用 `licenseConfigs`),补进最新发现的 SA 无法下载文件和 Search-vs-DR 区分。中英双语。
- **2026-07-06** — Deep Research 计数两处一致性修复:(a) `v_data_access_summary.deep_research_calls` 之前把 `AsyncAssist` (提交) **和** `ReadAsyncAssist` (UI 轮询) 都算进去,单用户被虚高 3-5 倍。现在跟 `v_daily_usage_per_user` 对齐 —— 只算提交。两天各跑 2 次 DR 的用户,Quota 页和 User Deep Dive 都显示 `4`,不再出现 `4` vs `12` 的不一致。(b) 全面 audit method 名后确认:Deep Research (`AssistantService.AsyncAssist`)、Google 搜索 API (`SearchService.Search`)、grounded chat 搜索 (`ConversationalSearchService.GetAnswer`) 是**三个独立 service**,我们的计数器分开桶,Deep Research 永远不会跟搜索混。
- **2026-07-06** — README 前置条件章节新增完整的端到端验证清单 (~14 项),让第一次部署的人明确知道啥时候算真正 green,包含手动 GE 控制台 toggle 和"等日志流过来再重跑 view"这个环节。中英双语。
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


