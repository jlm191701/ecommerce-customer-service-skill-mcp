import { ChangeEvent, ClipboardEvent, FormEvent, useState } from "react";
import { login, register, sendChatMessage } from "./api";
import type { AuthUser, ChatMessage, ChatResponse } from "./types";

type StoredSession = {
  id: string;
  name: string;
  messages: ChatMessage[];
  updatedAt: number;
};

type OrderProfile = {
  id: string;
  product: string;
  sku: string;
  status: string;
};

const SESSION_STORAGE_KEY = "aurora_customer_service_sessions";
const ACTIVE_SESSION_STORAGE_KEY = "aurora_customer_service_active_session";
const AUTH_STORAGE_KEY = "aurora_customer_service_user";

const orderProfiles: Record<string, OrderProfile> = {
  "64575145823542368": {
    id: "64575145823542368",
    product: "Aurora Phone X1",
    sku: "12GB + 256GB 曜石黑",
    status: "派送中",
  },
  "202606030001": {
    id: "202606030001",
    product: "Aurora Buds Pro",
    sku: "星云白",
    status: "已签收",
  },
  "202606030002": {
    id: "202606030002",
    product: "Aurora Pad Air",
    sku: "11 英寸 256GB 深空灰",
    status: "待发货",
  },
};

function createConversationId() {
  return `conv_${crypto.randomUUID()}`;
}

const initialAssistantMessage: ChatMessage = {
  role: "assistant",
  content:
    "您好，我是 Aurora Digital 在线客服。您可以咨询订单物流、商品参数、价保政策、售后处理或人工客服。",
};

function createSession(name = "新的客服会话"): StoredSession {
  return {
    id: createConversationId(),
    name,
    messages: [initialAssistantMessage],
    updatedAt: Date.now(),
  };
}

function loadSessions(): StoredSession[] {
  try {
    const raw = localStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return [createSession()];
    const parsed = JSON.parse(raw) as StoredSession[];
    if (!Array.isArray(parsed) || parsed.length === 0) return [createSession()];
    return parsed;
  } catch {
    return [createSession()];
  }
}

function loadAuthUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

function makeSessionName(message: string) {
  const compact = message.trim().replace(/\s+/g, " ");
  return compact.length > 18 ? `${compact.slice(0, 18)}...` : compact || "新的客服会话";
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function initializeSessions() {
  const loadedSessions = loadSessions();
  const savedActiveId = localStorage.getItem(ACTIVE_SESSION_STORAGE_KEY);
  const activeId =
    savedActiveId && loadedSessions.some((session) => session.id === savedActiveId)
      ? savedActiveId
      : loadedSessions[0].id;
  localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(loadedSessions));
  localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, activeId);
  return { loadedSessions, activeId };
}

function quickMessagesFor(user: AuthUser) {
  const orderQuestion = user.recent_order_id
    ? `我的订单 ${user.recent_order_id} 现在什么情况？`
    : "我想查询我的订单";
  return [
    orderQuestion,
    "Aurora Phone X1 支持多少瓦快充？",
    "我想了解数码产品价保政策",
    "我要人工客服",
  ];
}

function AuthScreen({ onAuthed }: { onAuthed: (user: AuthUser) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [account, setAccount] = useState("小蒋");
  const [userId, setUserId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("123456");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      const response =
        mode === "login"
          ? await login(account, password)
          : await register({
              user_id: userId.trim(),
              display_name: displayName.trim(),
              password,
            });
      localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(response.user));
      onAuthed(response.user);
    } catch (caught) {
      const detail = caught instanceof Error ? caught.message : "未知错误";
      setError(detail);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-shell">
      <section className="auth-card">
        <div className="brand-block">
          <div className="brand-mark">A</div>
          <div>
            <h1>Aurora Digital</h1>
            <p>数码商城账户中心</p>
          </div>
        </div>

        <div className="auth-tabs">
          <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")} type="button">
            登录
          </button>
          <button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")} type="button">
            注册
          </button>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === "login" ? (
            <label>
              账号 / 昵称
              <input value={account} onChange={(event) => setAccount(event.target.value)} />
            </label>
          ) : (
            <>
              <label>
                用户 ID
                <input value={userId} onChange={(event) => setUserId(event.target.value)} />
              </label>
              <label>
                昵称
                <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
              </label>
            </>
          )}
          <label>
            密码
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {error ? <div className="error auth-error">登录失败：{error}</div> : null}
          <button disabled={isSubmitting} type="submit">
            {isSubmitting ? "处理中" : mode === "login" ? "登录并进入客服" : "注册并进入客服"}
          </button>
        </form>

        <p className="auth-hint">演示账号：小蒋 / 林小北 / 周明，默认密码 123456。</p>
      </section>
    </main>
  );
}

export function App() {
  const [initialState] = useState(initializeSessions);
  const [sessions, setSessions] = useState<StoredSession[]>(initialState.loadedSessions);
  const [activeSessionId, setActiveSessionId] = useState(initialState.activeId);
  const [authUser, setAuthUser] = useState<AuthUser | null>(loadAuthUser);
  const [input, setInput] = useState("");
  const [selectedImage, setSelectedImage] = useState<{ name: string; dataUrl: string } | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastResponse, setLastResponse] = useState<ChatResponse | null>(null);

  const activeSession = sessions.find((session) => session.id === activeSessionId) ?? sessions[0];
  const messages = activeSession.messages;
  const conversationId = activeSession.id;

  if (!authUser) {
    return <AuthScreen onAuthed={setAuthUser} />;
  }

  const currentUser = authUser;
  const recentOrder = currentUser.recent_order_id ? orderProfiles[currentUser.recent_order_id] : null;
  const quickMessages = quickMessagesFor(currentUser);

  function persist(nextSessions: StoredSession[], nextActiveId = activeSessionId) {
    setSessions(nextSessions);
    setActiveSessionId(nextActiveId);
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(nextSessions));
    localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, nextActiveId);
  }

  function updateActiveSession(
    updater: (session: StoredSession) => StoredSession,
    nextActiveId = activeSessionId,
  ) {
    setSessions((current) => {
      const nextSessions = current.map((session) =>
        session.id === nextActiveId ? updater(session) : session,
      );
      localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(nextSessions));
      return nextSessions;
    });
    setActiveSessionId(nextActiveId);
    localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, nextActiveId);
  }

  async function submitMessage(message: string, image = selectedImage) {
    const trimmed = message.trim();
    if ((!trimmed && !image) || isSending) return;

    setInput("");
    setSelectedImage(null);
    setError(null);
    setIsSending(true);
    const displayMessage = trimmed || "请帮我看看这张图片";
    const shouldRename = activeSession.name === "新的客服会话";
    updateActiveSession((session) => ({
      ...session,
      name: shouldRename ? makeSessionName(displayMessage) : session.name,
      messages: [
        ...session.messages,
        { role: "user", content: displayMessage, imageUrl: image?.dataUrl },
      ],
      updatedAt: Date.now(),
    }));

    try {
      const response = await sendChatMessage({
        conversation_id: conversationId,
        user_id: currentUser.user_id,
        channel: "web",
        message: displayMessage,
        context: image ? { images: [{ name: image.name, data_url: image.dataUrl }] } : {},
        stream: false,
      });
      setLastResponse(response);
      updateActiveSession((session) => ({
        ...session,
        messages: [...session.messages, { role: "assistant", content: response.answer }],
        updatedAt: Date.now(),
      }));
    } catch (caught) {
      const detail = caught instanceof Error ? caught.message : "未知错误";
      setError(detail);
    } finally {
      setIsSending(false);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await submitMessage(input);
  }

  async function selectImageFile(file: File) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("请选择图片文件。");
      return;
    }
    if (file.size > 4 * 1024 * 1024) {
      setError("图片不能超过 4MB。");
      return;
    }
    setError(null);
    const dataUrl = await fileToDataUrl(file);
    setSelectedImage({ name: file.name, dataUrl });
  }

  async function handleImageChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) {
      await selectImageFile(file);
    }
  }

  async function handlePaste(event: ClipboardEvent<HTMLInputElement>) {
    const imageItem = Array.from(event.clipboardData.items).find((item) =>
      item.type.startsWith("image/"),
    );
    const file = imageItem?.getAsFile();
    if (!file) return;
    event.preventDefault();
    await selectImageFile(file);
  }

  function createNewConversation() {
    const nextSession = createSession();
    setLastResponse(null);
    persist([nextSession, ...sessions], nextSession.id);
    setError(null);
  }

  function selectSession(sessionId: string) {
    setActiveSessionId(sessionId);
    localStorage.setItem(ACTIVE_SESSION_STORAGE_KEY, sessionId);
    setLastResponse(null);
    setError(null);
  }

  function deleteSession(sessionId: string) {
    const remaining = sessions.filter((session) => session.id !== sessionId);
    const nextSessions = remaining.length > 0 ? remaining : [createSession()];
    const nextActiveId = sessionId === activeSessionId ? nextSessions[0].id : activeSessionId;
    persist(nextSessions, nextActiveId);
    setLastResponse(null);
    setError(null);
  }

  function logout() {
    localStorage.removeItem(AUTH_STORAGE_KEY);
    setAuthUser(null);
    setLastResponse(null);
  }

  const latestAction = lastResponse?.actions[lastResponse.actions.length - 1];
  const traceEvents = lastResponse?.trace_events ?? [];
  const sortedSessions = [...sessions].sort((a, b) => b.updatedAt - a.updatedAt);

  return (
    <main className="app-shell">
      <section className="workspace" aria-label="Aurora Digital 在线客服">
        <aside className="side-panel customer-panel">
          <div className="brand-block">
            <div className="brand-mark">A</div>
            <div>
              <h1>Aurora Digital</h1>
              <p>数码商城客服中心</p>
            </div>
          </div>

          <div className="section-block">
            <div className="section-title">客户上下文</div>
            <div className="info-row">
              <span>当前客户</span>
              <strong>{currentUser.display_name}</strong>
            </div>
            <div className="info-row">
              <span>账户 ID</span>
              <strong>{currentUser.user_id}</strong>
            </div>
            <div className="info-row">
              <span>会员状态</span>
              <strong>{currentUser.member_level}</strong>
            </div>
            <button className="logout-button" type="button" onClick={logout}>
              退出登录
            </button>
          </div>

          <div className="section-block order-card">
            <div className="section-title">最近订单</div>
            {recentOrder ? (
              <>
                <strong>{recentOrder.product}</strong>
                <span>{recentOrder.sku}</span>
                <div className="order-meta">
                  <span>订单号</span>
                  <code>{recentOrder.id}</code>
                </div>
                <div className="order-status">{recentOrder.status}</div>
              </>
            ) : (
              <div className="empty-order">
                <strong>暂无最近订单</strong>
                <span>注册用户还没有演示订单，可咨询商品、价保、售后或人工客服。</span>
              </div>
            )}
          </div>

          <div className="section-block">
            <div className="section-title">会话记录</div>
            <div className="session-list">
              {sortedSessions.map((session) => (
                <div className={session.id === activeSessionId ? "active" : ""} key={session.id}>
                  <button className="session-select" type="button" onClick={() => selectSession(session.id)}>
                    <strong>{session.name}</strong>
                    <span>{session.messages.length} 条消息</span>
                  </button>
                  <button
                    aria-label={`删除会话 ${session.name}`}
                    className="session-delete"
                    type="button"
                    onClick={() => deleteSession(session.id)}
                  >
                    删除
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="section-block">
            <div className="section-title">快捷问题</div>
            <div className="quick-list">
              {quickMessages.map((message) => (
                <button key={message} type="button" onClick={() => void submitMessage(message)} disabled={isSending}>
                  {message}
                </button>
              ))}
            </div>
          </div>
        </aside>

        <section className="chat-panel">
          <header className="chat-header">
            <div>
              <div className="eyebrow">在线客服</div>
              <h2>{activeSession.name}</h2>
            </div>
            <div className="header-actions">
              <button className="ghost-button" onClick={createNewConversation} type="button">
                新会话
              </button>
            </div>
          </header>

          <div className="message-list">
            {messages.map((message, index) => (
              <article className={`message ${message.role}`} key={`${message.role}-${index}`}>
                <div className="avatar">{message.role === "assistant" ? "AD" : "我"}</div>
                <div className="bubble">
                  {message.imageUrl ? (
                    <img className="message-image" src={message.imageUrl} alt="用户上传图片" />
                  ) : null}
                  <p>{message.content}</p>
                </div>
              </article>
            ))}
            {isSending ? (
              <article className="message assistant">
                <div className="avatar">AD</div>
                <div className="bubble pending">
                  <span />
                  <span />
                  <span />
                </div>
              </article>
            ) : null}
          </div>

          {error ? <div className="error">请求失败：{error}</div> : null}

          <form className="composer" onSubmit={handleSubmit}>
            {selectedImage ? (
              <div className="image-preview">
                <img src={selectedImage.dataUrl} alt="待发送图片" />
                <span>{selectedImage.name}</span>
                <button type="button" onClick={() => setSelectedImage(null)}>
                  移除
                </button>
              </div>
            ) : null}
            <label className="image-button" title="上传图片或截图" aria-label="上传图片或截图">
              +
              <input accept="image/*" type="file" onChange={(event) => void handleImageChange(event)} />
            </label>
            <input
              aria-label="消息"
              placeholder="输入订单号、商品参数、价保、售后，或粘贴截图"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onPaste={(event) => void handlePaste(event)}
            />
            <button disabled={isSending || (!input.trim() && !selectedImage)} type="submit">
              {isSending ? "发送中" : "发送"}
            </button>
          </form>
        </section>

        <aside className="side-panel agent-panel">
          <div className="section-block">
            <div className="section-title">Agent 状态</div>
            <div className="metric-grid">
              <div>
                <span>技能</span>
                <strong>{latestAction ? lastResponse?.conversation_state.active_skill : "-"}</strong>
              </div>
              <div>
                <span>意图</span>
                <strong>{latestAction ? lastResponse?.conversation_state.active_intent : "-"}</strong>
              </div>
            </div>
          </div>

          <div className="section-block">
            <div className="section-title">最近动作</div>
            {latestAction ? (
              <div className="action-card">
                <strong>{latestAction.name}</strong>
                <span>{latestAction.type}</span>
                <em data-status={latestAction.status}>{latestAction.status}</em>
              </div>
            ) : (
              <p className="muted">暂无动作</p>
            )}
          </div>

          <div className="section-block">
            <div className="section-title">Trace</div>
            {lastResponse ? (
              <>
                <code className="trace-id">{lastResponse.trace_id}</code>
                <div className="trace-list">
                  {traceEvents.slice(-6).map((event) => (
                    <div key={`${event.sequence}-${event.event}`}>
                      <span>{event.sequence}</span>
                      <strong>{event.event}</strong>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="muted">等待首条消息</p>
            )}
          </div>
        </aside>
      </section>
    </main>
  );
}
