# GE 生成能力 API 探测

## 在试什么

用 **服务账号** 直接调 Gemini Enterprise 的 API,看以下三件事能不能走 API (不走 UI):

1. **Chat** — `StreamAssist` 触发普通聊天,拿回响应文本
2. **Image generation** — Prompt 请求生图,看 GE 后端是不是真的生成一张图片、通过响应返回
3. **Video generation** — 同上,请求视频

以及对比:
- 直接调 Vertex AI 的 `imagen` / `veo` (绕过 GE),看效果如何
- Deep Research 的 `AsyncAssist` 能不能提交

## 为啥要试

我们 dashboard 里 **image_gen / video_gen 只能靠 prompt 关键词猜**,因为观察层面 GE 后端不发 audit log。但**别人如果想集成 GE 到自己的服务**,他们关心的不是"能不能观察",而是"**能不能程序化触发**"。所以要实测。

## 结果速览 (2026-07-03)

见 `results/` 目录下每个探针的原始输出 + `FINDINGS.md`。

## 运行

```bash
cd playground/ge-generation-probe
./run_probes.sh
```

不 import contexts.*,不引入外部依赖。用 `gcloud auth print-access-token` + `curl` + `python3` stdlib。
