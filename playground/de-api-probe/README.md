# Discovery Engine API Probe — playground

在试什么：

1. **Deep Research resource-name detection**: 
   已知 GE Doc 说 Deep Research 可以通过 `resourceName LIKE '%/agents/deep_research%'` 检测。
   之前我们只按 `methodName LIKE '%AsyncAssist'` 抓。测这两个 pattern 差异：会不会有事件
   走别的 method 但落到 deep_research agent 上？

2. **NotebookLM SA 授权测试**:
   建 custom role 加 `discoveryengine.notebooks.{list,create,get}` 权限,授给 sim SA,
   实测 CreateNotebook / ListNotebooks 能否真跑通。

3. **Discovery Engine 全 API surface probe**:
   系统 GET 一遍 v1/v1alpha/v1beta 的常用 collection 端点,看还有什么 method 我们
   没用上。

不要 import contexts.* — 只写脚本 + 记录。
