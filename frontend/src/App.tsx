import { Button, Empty, Layout, message, Popconfirm } from "antd";
import { useCallback, useEffect, useState } from "react";
import { createSession, deleteSession, listSessions, type AuthUser, type ChatSession } from "./api/client";
import { Chat } from "./pages/Chat";
import { Knowledge } from "./pages/Knowledge";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";

const { Header, Content, Sider } = Layout;

const TEXT = {
  loadSessionsFailed: "会话加载失败",
  createSessionFailed: "新建对话失败",
  deleteSuccess: "已删除对话",
  deleteFailed: "删除对话失败",
  newChat: "新建对话",
  noSessions: "暂无会话",
  untitled: "未命名对话",
  deleteTitle: "删除对话",
  deleteDescription: "确定删除这条历史对话吗？",
  delete: "删除",
  cancel: "取消",
  appTitle: "企业智能客服系统",
  logout: "退出",
  mainFeatures: "主功能",
  conversations: "对话",
  chat: "智能问答",
  knowledge: "知识管理"
};

function readStoredUser(): AuthUser | null {
  const raw = localStorage.getItem("user");
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    localStorage.removeItem("user");
    return null;
  }
}

export function App() {
  const [user, setUser] = useState<AuthUser | null>(() => readStoredUser());
  const [authPage, setAuthPage] = useState<"login" | "register">("login");
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);
  const [activeView, setActiveView] = useState<"chat" | "knowledge">("chat");

  const loadSessions = useCallback(async () => {
    if (!localStorage.getItem("token")) return;
    try {
      const items = await listSessions();
      setSessions(items);
      setSelectedSessionId((current) => current ?? items[0]?.id ?? null);
    } catch (error) {
      message.error(error instanceof Error ? error.message : TEXT.loadSessionsFailed);
    }
  }, []);

  useEffect(() => {
    if (user) loadSessions();
  }, [user, loadSessions]);

  const handleAuthSuccess = (token: string, nextUser: AuthUser) => {
    localStorage.setItem("token", token);
    localStorage.setItem("user", JSON.stringify(nextUser));
    setUser(nextUser);
  };

  const logout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    setSessions([]);
    setSelectedSessionId(null);
    setUser(null);
    setAuthPage("login");
  };

  const newChat = async () => {
    try {
      const session = await createSession();
      setSelectedSessionId(session.id);
      await loadSessions();
    } catch (error) {
      message.error(error instanceof Error ? error.message : TEXT.createSessionFailed);
    }
  };

  const removeSession = async (sessionId: number) => {
    try {
      await deleteSession(sessionId);
      const nextSessions = sessions.filter((item) => item.id !== sessionId);
      setSessions(nextSessions);
      if (selectedSessionId === sessionId) {
        setSelectedSessionId(nextSessions[0]?.id ?? null);
      }
      message.success(TEXT.deleteSuccess);
      await loadSessions();
    } catch (error) {
      message.error(error instanceof Error ? error.message : TEXT.deleteFailed);
    }
  };

  if (!user) {
    return authPage === "login" ? (
      <Login onSuccess={handleAuthSuccess} onGoRegister={() => setAuthPage("register")} />
    ) : (
      <Register onSuccess={handleAuthSuccess} onGoLogin={() => setAuthPage("login")} />
    );
  }

  return (
    <Layout className="app-shell">
      <Sider width={280} theme="light" className="session-sidebar">
        <div className="brand">AegisDesk AI</div>
        <div className="sidebar-section">
          <div className="sidebar-section-title">{TEXT.mainFeatures}</div>
          <div className="main-nav">
            <Button block type={activeView === "chat" ? "primary" : "default"} onClick={() => setActiveView("chat")}>
              {TEXT.chat}
            </Button>
            <Button block type={activeView === "knowledge" ? "primary" : "default"} onClick={() => setActiveView("knowledge")}>
              {TEXT.knowledge}
            </Button>
          </div>
        </div>
        {activeView === "chat" ? (
          <div className="sidebar-section conversation-section">
            <div className="sidebar-section-title">{TEXT.conversations}</div>
            <div className="session-actions">
              <Button type="primary" block onClick={newChat}>
                + {TEXT.newChat}
              </Button>
            </div>
            <div className="session-list">
              {sessions.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={TEXT.noSessions} />
              ) : (
                sessions.map((session) => (
                  <div
                    key={session.id}
                    className={`session-item ${session.id === selectedSessionId ? "active" : ""}`}
                    onClick={() => setSelectedSessionId(session.id)}
                  >
                    <div className="session-main">
                      <span className="session-title">{session.title || TEXT.untitled}</span>
                      <span className="session-time">{new Date(session.updated_at).toLocaleString()}</span>
                    </div>
                    <Popconfirm
                      title={TEXT.deleteTitle}
                      description={TEXT.deleteDescription}
                      okText={TEXT.delete}
                      cancelText={TEXT.cancel}
                      onConfirm={(event) => {
                        event?.stopPropagation();
                        removeSession(session.id);
                      }}
                      onCancel={(event) => event?.stopPropagation()}
                    >
                      <Button
                        size="small"
                        type="text"
                        className="session-delete"
                        onClick={(event) => event.stopPropagation()}
                      >
                        {TEXT.delete}
                      </Button>
                    </Popconfirm>
                  </div>
                ))
              )}
            </div>
          </div>
        ) : null}
      </Sider>
      <Layout>
        <Header className="topbar">
          <span>{TEXT.appTitle}</span>
          <div className="userbar">
            <span>{user.email || user.phone}</span>
            <Button size="small" onClick={logout}>
              {TEXT.logout}
            </Button>
          </div>
        </Header>
        <Content className="content">
          {activeView === "chat" ? (
            <Chat
              sessionId={selectedSessionId}
              onSessionSelected={setSelectedSessionId}
              onSessionsChanged={loadSessions}
            />
          ) : (
            <Knowledge />
          )}
        </Content>
      </Layout>
    </Layout>
  );
}
