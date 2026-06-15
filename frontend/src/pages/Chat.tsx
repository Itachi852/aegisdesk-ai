import { Button, Empty, Input, Modal, message } from "antd";
import { useCallback, useEffect, useState } from "react";
import {
  getChatQuota,
  getSession,
  streamChat,
  submitFeedback,
  type ChatQuota,
  type ChatMessage,
  type FeedbackRating,
  type MessageSource
} from "../api/client";

type LocalMessage = {
  id?: number;
  role: "user" | "assistant";
  content: string;
  thinking?: boolean;
  intent?: string | null;
  feedback?: FeedbackRating;
  sources?: MessageSource[];
};

type ChatProps = {
  sessionId: number | null;
  onSessionSelected: (sessionId: number) => void;
  onSessionsChanged: () => void;
};

const TEXT = {
  loadFailed: "会话详情加载失败",
  quotaLoadFailed: "提问次数加载失败",
  empty: "选择会话，或新建对话后开始提问",
  placeholder: "请输入问题，最多 500 字",
  quotaReachedPlaceholder: "今日提问次数已达上限，请明天再试",
  send: "发送",
  answerNotSaved: "回答保存后才能反馈",
  feedbackSuccess: "反馈已提交",
  feedbackFailed: "反馈提交失败",
  like: "点赞",
  dislike: "踩",
  feedbackTitle: "补充反馈",
  submit: "提交",
  cancel: "取消",
  feedbackPlaceholder: "可选填：请说明这个回答哪里不理想",
  thinking: "正在思考...",
  answerFailed: "抱歉，当前暂时无法生成回答，请稍后再试。"
};

const INTENT_LABELS: Record<string, string> = {
  product_consultation: "产品咨询",
  after_sales: "售后问题",
  chat: "闲聊",
  complaint: "投诉",
  other: "其他"
};

function dedupeSources(sources: MessageSource[] = []) {
  const seen = new Set<string>();
  return sources.filter((source) => {
    const key = String(source.document_id || source.doc_name || source.chunk_id);
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function toLocalMessage(item: ChatMessage): LocalMessage {
  return {
    id: item.id,
    role: item.role === "user" ? "user" : "assistant",
    content: item.content,
    intent: item.intent || undefined,
    feedback: item.feedback || undefined,
    sources: dedupeSources(item.sources || [])
  };
}

export function Chat({ sessionId, onSessionSelected, onSessionsChanged }: ChatProps) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [quota, setQuota] = useState<ChatQuota | null>(null);
  const [feedbackTarget, setFeedbackTarget] = useState<{ index: number; rating: FeedbackRating } | null>(null);
  const [feedbackComment, setFeedbackComment] = useState("");
  const quotaReached = quota ? !quota.available : false;

  const loadQuota = useCallback(async () => {
    try {
      setQuota(await getChatQuota());
    } catch (error) {
      message.error(error instanceof Error ? error.message : TEXT.quotaLoadFailed);
    }
  }, []);

  useEffect(() => {
    loadQuota();
  }, [loadQuota]);

  useEffect(() => {
    loadQuota();
  }, [sessionId, loadQuota]);

  useEffect(() => {
    const refreshQuota = () => {
      if (document.visibilityState === "visible") {
        loadQuota();
      }
    };
    document.addEventListener("visibilitychange", refreshQuota);
    window.addEventListener("focus", loadQuota);
    return () => {
      document.removeEventListener("visibilitychange", refreshQuota);
      window.removeEventListener("focus", loadQuota);
    };
  }, [loadQuota]);

  useEffect(() => {
    if (loading) return;

    if (!sessionId) {
      setMessages([]);
      return;
    }

    getSession(sessionId)
      .then((session) => setMessages(session.messages.map(toLocalMessage)))
      .catch((error) => message.error(error instanceof Error ? error.message : TEXT.loadFailed));
  }, [sessionId, loading]);

  const send = () => {
    const text = question.trim();
    if (!text || loading || quotaReached) return;

    setQuestion("");
    setLoading(true);
    setMessages((prev) => [
      ...prev,
      { role: "user", content: text },
      { role: "assistant", content: TEXT.thinking, thinking: true }
    ]);

    streamChat({
      question: text,
      sessionId,
      onSession: (sessionEvent) => {
        onSessionSelected(sessionEvent.session_id);
        setMessages((prev) => {
          const next = [...prev];
          for (let index = next.length - 1; index >= 0; index -= 1) {
            if (next[index].role === "user" && next[index].content === text && !next[index].id) {
              next[index] = {
                ...next[index],
                id: sessionEvent.user_message_id,
                intent: sessionEvent.intent || undefined
              };
              break;
            }
          }
          return next;
        });
      },
      onProgress: (progressEvent) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === "assistant" && last.thinking) {
            next[next.length - 1] = { ...last, content: progressEvent.message };
          }
          return next;
        });
      },
      onDelta: (delta) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (!last || last.role !== "assistant") {
            return [...next, { role: "assistant", content: delta }];
          }
          if (last.thinking) {
            next[next.length - 1] = { ...last, content: delta, thinking: false };
            return next;
          }
          next[next.length - 1] = { ...last, content: last.content + delta };
          return next;
        });
      },
      onSaved: (messageId) => {
        setMessages((prev) => {
          const next = [...prev];
          for (let index = next.length - 1; index >= 0; index -= 1) {
            if (next[index].role === "assistant" && !next[index].id) {
              next[index] = { ...next[index], id: messageId };
              break;
            }
          }
          return next;
        });
      },
      onSources: (sources) => {
        setMessages((prev) => {
          const next = [...prev];
          for (let index = next.length - 1; index >= 0; index -= 1) {
            if (next[index].role === "assistant") {
              next[index] = { ...next[index], sources: dedupeSources(sources) };
              break;
            }
          }
          return next;
        });
      },
      onDone: () => {
        setLoading(false);
        loadQuota();
        onSessionsChanged();
      },
      onError: (errorMessage) => {
        message.error(errorMessage || TEXT.answerFailed);
        loadQuota();
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === "assistant" && last.thinking) {
            next.pop();
          }
          const previous = next[next.length - 1];
          if (previous?.role === "user" && previous.content === text && !previous.id) {
            next.pop();
          }
          return next;
        });
      }
    });
  };

  const sendFeedback = async (index: number, rating: FeedbackRating, comment?: string) => {
    const target = messages[index];
    if (!target?.id) {
      message.warning(TEXT.answerNotSaved);
      return;
    }
    try {
      await submitFeedback({ message_id: target.id, rating, comment });
      setMessages((prev) => prev.map((item, itemIndex) => (itemIndex === index ? { ...item, feedback: rating } : item)));
      message.success(TEXT.feedbackSuccess);
    } catch (error) {
      message.error(error instanceof Error ? error.message : TEXT.feedbackFailed);
    }
  };

  const confirmTextFeedback = async () => {
    if (!feedbackTarget) return;
    await sendFeedback(feedbackTarget.index, feedbackTarget.rating, feedbackComment.trim());
    setFeedbackTarget(null);
    setFeedbackComment("");
  };

  return (
    <div className="chat-page">
      <div className="message-list">
        {messages.length === 0 ? (
          <div className="empty-chat">
            <Empty description={TEXT.empty} />
          </div>
        ) : (
          messages.map((item, index) => (
            <div key={index} className={`message-row ${item.role}`}>
              <div className={`message ${item.role} ${item.thinking ? "thinking" : ""}`}>{item.content}</div>
              {item.role === "user" && item.intent ? (
                <div className="message-intent">{INTENT_LABELS[item.intent] || "其他"}</div>
              ) : null}
              {item.role === "assistant" && item.content && !item.thinking ? (
                <div className="feedback-actions">
                  <Button
                    size="small"
                    type="default"
                    className={`feedback-button ${item.feedback === "like" ? "active" : ""}`}
                    onClick={() => sendFeedback(index, "like")}
                  >
                    {TEXT.like}
                  </Button>
                  <Button
                    size="small"
                    type="default"
                    className={`feedback-button ${item.feedback === "dislike" ? "active" : ""}`}
                    onClick={() => setFeedbackTarget({ index, rating: "dislike" })}
                  >
                    {TEXT.dislike}
                  </Button>
                </div>
              ) : null}
            </div>
          ))
        )}
      </div>
      <div className="composer">
        {quotaReached ? (
          <div className="quota-hint">
            今日提问次数已达上限（{quota?.limit} 次），请明天再试。
          </div>
        ) : null}
        <Input.TextArea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onPressEnter={(event) => {
            if (!event.shiftKey) {
              event.preventDefault();
              send();
            }
          }}
          maxLength={500}
          autoSize={{ minRows: 2, maxRows: 4 }}
          disabled={quotaReached}
          placeholder={quotaReached ? TEXT.quotaReachedPlaceholder : TEXT.placeholder}
        />
        <Button type="primary" disabled={loading || quotaReached} onClick={send}>
          {TEXT.send}
        </Button>
      </div>
      <Modal
        title={TEXT.feedbackTitle}
        open={feedbackTarget !== null}
        okText={TEXT.submit}
        cancelText={TEXT.cancel}
        onOk={confirmTextFeedback}
        onCancel={() => {
          setFeedbackTarget(null);
          setFeedbackComment("");
        }}
      >
        <Input.TextArea
          value={feedbackComment}
          onChange={(event) => setFeedbackComment(event.target.value)}
          maxLength={500}
          showCount
          autoSize={{ minRows: 3, maxRows: 5 }}
          placeholder={TEXT.feedbackPlaceholder}
        />
      </Modal>
    </div>
  );
}
