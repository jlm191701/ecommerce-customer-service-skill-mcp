export type ChatRequest = {
  conversation_id: string;
  user_id: string;
  message: string;
  tenant_id?: string;
  brand_id?: string;
  channel: "web";
  context?: Record<string, unknown>;
  stream?: boolean;
};

export type ConversationState = {
  active_skill: string | null;
  active_intent: string | null;
  summary: string;
  task_state: Record<string, unknown>;
  recent_messages?: Array<{
    role: "user" | "assistant";
    content: string;
  }>;
  long_term_memory?: string;
};

export type ChatResponse = {
  answer: string;
  conversation_state: ConversationState;
  actions: Array<{
    type: string;
    name: string;
    status: string;
    summary?: string | null;
  }>;
  handoff_status: {
    required: boolean;
    reason: string | null;
  };
  trace_id: string;
  trace_events?: Array<{
    sequence: number;
    event: string;
    step?: number | null;
    details: Record<string, unknown>;
  }>;
};

export type ChatMessage = {
  role: "assistant" | "user";
  content: string;
  imageUrl?: string;
  meta?: string;
};

export type AuthUser = {
  user_id: string;
  display_name: string;
  member_level: string;
  recent_order_id?: string | null;
};

export type AuthResponse = {
  user: AuthUser;
};
