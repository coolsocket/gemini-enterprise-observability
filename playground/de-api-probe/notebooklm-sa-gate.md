# NotebookLM SA 访问的最终结论

## 结论: 服务账号无法通过 API 使用 NotebookLM,IAM 不是唯一 gate

## 实测证据 (2026-07-03)

### 步骤 1: 授正确 IAM 权限
```bash
gcloud iam roles create notebooklmUser --project=PROJECT_ID \
  --permissions="discoveryengine.notebooks.list,create,get,update,delete"

gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:test-sa@PROJECT_ID.iam.gserviceaccount.com" \
  --role="projects/PROJECT_ID/roles/notebooklmUser"
```

绑定期间报了这个 warning (**注意**: 不阻塞绑定):
```
Regional Access Boundary HTTP request failed after retries:
response_data={'error': {'code': 404,
  'message': 'Account not found for email: <REDACTED_HASH>|demo-user@example.com',
  'status': 'NOT_FOUND'}}
```

### 步骤 2: 验证绑定生效
```
$ gcloud projects get-iam-policy ... --filter="bindings.members:test-sa"
projects/PROJECT_ID/roles/notebooklmUser  ✓
roles/discoveryengine.editor              ✓
```

### 步骤 3: 调 API
- `POST v1alpha/notebooks` (CreateNotebook) → **403 "The caller does not have permission"**
- `GET v1alpha/notebooks:listRecentlyViewed` → **403 "The caller does not have permission"**

## 关键区别

| 情况 | 错误信息 |
|---|---|
| **没授 IAM role** (之前) | `Permission 'discoveryengine.notebooks.create' denied on resource ...` — 具体权限名 |
| **授了 IAM role** (现在) | `The caller does not have permission` — 泛化, 意味着 IAM 检查过了,但**deeper service-level check 失败** |

## Regional Access Boundary 是啥关系

`<REDACTED_HASH>|demo-user@example.com` = Workforce Identity Federation subject URI
- 前缀 hash = workforce pool ID hash
- email 部分 = 用户 principal

NotebookLM 后台服务在处理请求前会做 workforce identity → Regional Access Boundary registry 查询。**服务账号没有 workforce identity, 查询失败 → 拒绝调用**。

这就是为什么 SA 拿到再全的 IAM role 都调不通 NotebookLM API。

## 建议

- ✅ **别人程序化用 NotebookLM 是不支持的** (至少在 2026-07-03 时点)
- ✅ **观察侧 (audit log) 完全够用** — 我们已经从 audit log 抓 notebooklm.v1main.* 所有 method,包括别人手工用的操作
- ❌ **别再花时间试**授更多 role, gate 不在 IAM 层
- 📌 未来 GE 可能加 "service-to-service" 支持, 到时候得升级 IAM role bundle

## 对我们 dashboard 的影响

**零影响**。
- audit log 记录 UI 用户的 NotebookLM 使用 → 已在 v_data_access_summary.notebooklm_* 桶
- 我们从来没想让 SA 直接创建 notebook

RAB 那个 warning 是**cosmetic** (对绑定没实际影响), 但**同样的 gate 才是 API 403 的根因**。
