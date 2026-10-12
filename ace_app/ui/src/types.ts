export type Target = "local" | "server";
export type OperationState = "idle" | "recording" | "sending" | "clearing" | "shutting_down";

export interface Turn {
  role?: "user" | "assistant" | "ace";
  speaker?: string;
  text?: string;
  content?: string;
  timestamp?: string;
  created_at?: string;
  user_text?: string;
  assistant_text?: string;
}

export interface WidgetRecord {
  id: string;
  html: string;
  source_target: Target;
  created_at?: string;
  updated_at?: string;
  revision?: number;
}

export interface Notice {
  id?: string;
  level?: "info" | "success" | "warning" | "error";
  message: string;
  details?: string;
}

export interface Snapshot {
  schema_version: number;
  revision: number;
  active_target: Target;
  operation: { state: OperationState; started_at?: string; target?: Target };
  history: { turns: Turn[]; assumed_context_turns: number };
  widgets: WidgetRecord[];
  connections: Record<string, string>;
  notices: Notice[];
}

export type Envelope<T = unknown> =
  | { ok: true; value: T }
  | { ok: false; error: { code: string; message: string } };
