import { Button, Empty, Layout, message, Popconfirm } from "antd";
import { useCallback, useEffect, useState } from "react";
import { createSession, deleteSession, listSessions, type AuthUser, type ChatSession } from "./api/client";
import { Chat } from "./pages/Chat";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";

const { Header, Content, Sider } = Layout;

const TEXT = {
  loadSessionsFailed: "\u4f1a\u8bdd\u52a0\u8f7d\u5931\u8d25",
  createSessionFailed: "\u65b0\u5efa\u5bf9\u8bdd\u5931\u8d25",
  deleteSuccess: "\u5df2\u5220\u9664\u5bf9\u8bdd",
  deleteFailed: "\u5220\u9664\u5bf9\u8bdd\u5931\u8d25",
  newChat: "\u65b0\u5efa\u5bf9\u8bdd",
  noSessions: "\u6682\u65e0\u4f1a\u8bdd",
  untitled: "\u672a\u547d\u540d\u5bf9\u8bdd",
  deleteTitle: "\u5220\u9664\u5bf9\u8bdd",
  deleteDescription: "\u786e\u5b9a\u5220\u9664\u8fd9\u6761\u5386\u53f2\u5bf9\u8bdd\u5417\uff1f",
  delete: "\u5220\u9664",
  cancel: "\u53d6\u6d88",
  appTitle: "\u4f01\u4e1a\u667a\u80fd\u5ba2\u670d\u7cfb\u7edf",
  logout: "\u9000\u51fa"
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
          <Chat
            sessionId={selectedSessionId}
            onSessionSelected={setSelectedSessionId}
            onSessionsChanged={loadSessions}
          />
        </Content>
      </Layout>
    </Layout>
  );
}
