import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, ConversationWithResponseRow } from "../api";
import { EmptyState, Panel } from "../components/Card";
import { fmtTs } from "../components/DataTable";
import { useOrigin } from "../origin";
import { useEngine } from "../engine";

const STATUS_TAG: Record<string, string> = {
  STOP:        "bg-ggreen/15 text-ggreen border-ggreen/30",
  MAX_TOKENS:  "bg-gyellow/15 text-gyellow border-gyellow/30",
  SAFETY:      "bg-gred/15   text-gred   border-gred/30",
  OTHER:       "bg-info/15   text-info   border-info/30",
  UNSPECIFIED: "bg-ink-muted/15 text-ink-muted border-ink-muted/30",
};

export default function Conversations() {
  const { origin } = useOrigin();
  const { engineId } = useEngine();
  const q = useQuery({
    queryKey: ["v_conversations_with_response", origin, engineId],
    queryFn: () => api.view<ConversationWithResponseRow>("v_conversations_with_response", origin, engineId),
  });

  // Group by session_id (fallback: each row its own)
  const sessions = (() => {
    const rows = q.data?.rows ?? [];
    const bySession: Record<string, ConversationWithResponseRow[]> = {};
    rows.forEach((r) => {
      const key = r.session_id ?? `__no_session_${r.prompt_trace_id}`;
      (bySession[key] ??= []).push(r);
    });
    return Object.entries(bySession)
      .map(([sid, turns]) => ({
        session_id: sid.startsWith("__no_session") ? null : sid,
        turns: turns.sort((a, b) => a.timestamp.localeCompare(b.timestamp)),
        actor: turns[0].actor_email,
        origin: turns[0].origin,
        engine: turns[0].engine_display_name ?? turns[0].engine_id_raw,
        first: turns[0].timestamp,
        last: turns[turns.length - 1].timestamp,
        has_any_response: turns.some((t) => t.join_status === "matched"),
      }))
      .sort((a, b) => b.last.localeCompare(a.last));
  })();

  const [openSession, setOpenSession] = useState<string | null>(null);

  return (
    <div className="space-y-3">
      {/* Data limitation banner — updated with verified findings */}
      <div className="rounded-xl border border-info/30 bg-info-bg/10 px-5 py-3 text-sm">
        <div className="text-ink-primary font-medium mb-1">📋 数据限制说明（已验证）</div>
        <ul className="text-xs text-ink-secondary space-y-0.5 list-disc list-inside">
          <li><b>多模态</b>：GE 的 <code className="bg-subtle px-1 rounded">streamAssist</code> v1alpha API 不接受 <code className="bg-subtle px-1 rounded">inlineData</code>，图片/文件走"先上传到 session files → chat 引用 file_id"。多模态使用量看 Data Access 页的 <b>session_files</b> 调用数</li>
          <li><b>无响应原因</b>：(1) 真人通过 GE 控制台 UI 调用走 <code className="bg-subtle px-1 rounded">v1main</code>，**该路径不写 <code>gen_ai.choice</code> 日志** → response 永远抓不到；(2) sim SA 通过 REST 调，client 提前断开 streaming 会导致 choice log 不完整</li>
          <li>prompt 和 response 用<b>精确 trace_id JOIN</b>（不再用时间窗模糊配对）</li>
          <li>response chunks 已按 trace_id 聚合（STOP 终结）+ 自动拼接 streaming 文本</li>
        </ul>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-4">
        {/* Left: session list */}
        <Panel title={`会话 (${sessions.length})`}>
          {q.isLoading ? <EmptyState title="加载中…" /> :
           sessions.length === 0 ? (
            <EmptyState title="没有会话" hint={origin ? "切到「全部」试试" : "等待 chat 流量"} />
          ) : (
            <ul className="divide-y divide-border-subtle -m-5">
              {sessions.map((s) => {
                const key = s.session_id ?? `none-${s.first}`;
                const isOpen = openSession === key;
                return (
                  <li key={key}>
                    <button
                      onClick={() => setOpenSession(isOpen ? null : key)}
                      className={`w-full text-left px-4 py-3 transition-colors ${
                        isOpen ? "bg-subtle" : "hover:bg-subtle/50"
                      }`}
                    >
                      <div className="flex items-baseline gap-2 mb-1">
                        <span className="text-xs text-ink-muted truncate font-mono flex-1">{s.actor}</span>
                        {!s.has_any_response && (
                          <span className="text-[10px] text-warn">⚠ 无响应</span>
                        )}
                      </div>
                      <div className="text-sm text-ink-primary truncate">{s.turns[0].prompt}</div>
                      <div className="text-[11px] text-ink-muted mt-1 flex gap-2">
                        <span>{s.turns.length} turn{s.turns.length > 1 ? "s" : ""}</span>
                        <span>·</span>
                        <span className="truncate">{s.engine ?? "—"}</span>
                        <span className="ml-auto shrink-0">{fmtTs(s.last)}</span>
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>

        {/* Right: selected session detail */}
        <Panel title={openSession ? `Session 详情 · ${openSession.slice(0, 16)}…` : "选择一个会话查看详情"}>
          {!openSession ? <EmptyState title="点左侧任一会话" /> : (() => {
            const session = sessions.find((s) => (s.session_id ?? `none-${s.first}`) === openSession);
            if (!session) return <EmptyState title="未找到" />;
            return (
              <div className="space-y-4">
                {session.turns.map((turn, i) => (
                  <div key={turn.prompt_trace_id} className="border border-border-subtle rounded-lg overflow-hidden">
                    {/* User prompt */}
                    <div className="px-4 py-3 bg-subtle/40 border-b border-border-subtle">
                      <div className="flex items-baseline gap-2 mb-1.5">
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border bg-gblue/10 text-gblue border-gblue/30">
                          USER
                        </span>
                        <span className="text-[11px] text-ink-muted font-mono">{fmtTs(turn.timestamp)}</span>
                        <span className="text-[11px] text-ink-muted ml-auto">turn {i + 1}</span>
                      </div>
                      <div className="text-sm text-ink-primary whitespace-pre-wrap break-words">{turn.prompt}</div>
                    </div>
                    {/* Model response */}
                    {turn.join_status === "no_response" ? (
                      <div className="px-4 py-3 text-xs">
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border bg-warn/10 text-warn border-warn/30 mr-2">
                          NO_RESPONSE
                        </span>
                        <span className="text-ink-muted italic">
                          5 分钟时间窗内没找到匹配的模型响应。原因：trace_id 链路断、或调用失败、或 v1main UI 路径不写 gen_ai.choice 日志。
                        </span>
                      </div>
                    ) : (
                      <>
                        {turn.reasoning_text && (
                          <div className="px-4 py-3 border-b border-border-subtle/40 bg-subtle/20">
                            <div className="flex items-baseline gap-2 mb-1.5">
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border bg-warn/10 text-warn border-warn/30">
                                REASONING
                              </span>
                              <span className="text-[11px] text-ink-muted">deep think</span>
                            </div>
                            <div className="text-xs text-ink-secondary whitespace-pre-wrap break-words font-mono">
                              {turn.reasoning_text}
                            </div>
                          </div>
                        )}
                        <div className="px-4 py-3">
                          <div className="flex items-baseline gap-2 mb-1.5">
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border bg-ggreen/10 text-ggreen border-ggreen/30">
                              MODEL
                            </span>
                            {turn.response_status && (
                              <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${STATUS_TAG[turn.response_status] ?? STATUS_TAG.UNSPECIFIED}`}>
                                {turn.response_status}
                              </span>
                            )}
                            <span className="text-[11px] text-ink-muted">{turn.chunk_count ?? 0} chunks</span>
                          </div>
                          <div className="text-sm text-ink-secondary whitespace-pre-wrap break-words">
                            {turn.response_text ?? "—"}
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                ))}
              </div>
            );
          })()}
        </Panel>
      </div>
    </div>
  );
}
