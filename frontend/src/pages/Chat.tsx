import { Button, Empty, Input, Modal, message } from "antd";
import { useEffect, useState } from "react";
import { getSession, streamChat, submitFeedback, type ChatMessage, type FeedbackRating } from "../api/client";

type LocalMessage = {
  id?: number;
  role: "user" | "assistant";
  content: string;
  feedback?: FeedbackRating;
};

type ChatProps = {
  sessionId: number | null;
  onSessionSelected: (sessionId: number) => void;
  onSessionsChanged: () => void;
};

const TEXT = {
  loadFailed: "\u4f1a\u8bdd\u8be6\u60c5\u52a0\u8f7d\u5931\u8d25",
  empty: "\u9009\u62e9\u4f1a\u8bdd\uff0c\u6216\u65b0\u5efa\u5bf9\u8bdd\u540e\u5f00\u59cb\u63d0\u95ee",
  placeholder: "\u8bf7\u8f93\u5165\u95ee\u9898\uff0c\u6700\u591a 500 \u5b57",
  send: "\u53d1\u9001",
  answerNotSaved: "\u56de\u7b54\u4fdd\u5b58\u540e\u624d\u80fd\u53cd\u9988",
  feedbackSuccess: "\u53cd\u9988\u5df2\u63d0\u4ea4",
  feedbackFailed: "\u53cd\u9988\u63d0\u4ea4\u5931\u8d25",
  like: "\u70b9\u8d5e",
  dislike: "\u8e29",
  feedbackTitle: "\u8865\u5145\u53cd\u9988",
  submit: "\u63d0\u4ea4",
  cancel: "\u53d6\u6d88",
  feedbackPlaceholder: "\u53ef\u9009\u586b\uff1a\u8bf7\u8bf4\u660e\u8fd9\u4e2a\u56de\u7b54\u54ea\u91cc\u4e0d\u7406\u60f3"
};

function toLocalMessage(item: ChatMessage): LocalMessage {
  return {
    id: item.id,
    role: item.role === "user" ? "user" : "assistant",
    content: item.content,
    feedback: item.feedback || undefined
  };
}

export function Chat({ sessionId, onSessionSelected, onSessionsChanged }: ChatProps) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [feedbackTarget, setFeedbackTarget] = useState<{ index: number; rating: FeedbackRating } | null>(null);
  const [feedbackComment, setFeedbackComment] = useState("");

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
    if (!text || loading) return;

    setQuestion("");
    setLoading(true);
    setMessages((prev) => [...prev, { role: "user", content: text }, { role: "assistant", content: "" }]);

    streamChat({
      question: text,
      sessionId,
      onSession: onSessionSelected,
      onDelta: (delta) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (!last || last.role !== "assistant") {
            return [...next, { role: "assistant", content: delta }];
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
      onDone: () => {
        setLoading(false);
        onSessionsChanged();
      },
      onError: (errorMessage) => message.error(errorMessage)
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
              <div className={`message ${item.role}`}>{item.content}</div>
              {item.role === "assistant" && item.content ? (
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
          placeholder={TEXT.placeholder}
        />
        <Button type="primary" loading={loading} onClick={send}>
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
