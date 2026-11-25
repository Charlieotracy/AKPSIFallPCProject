export type Module = "courses" | "uhs" | "cbtf" | "tickets";

export type Kind = "search" | "book" | "watch";

export type TaskStatus =
  | "needs_info"
  | "ready"
  | "searching"
  | "awaiting_login"
  | "candidates"
  | "awaiting_confirm"
  | "executing"
  | "watching"
  | "done"
  | "failed"
  | "handed_off"
  | "cancelled";

export interface Task {
  id: string;
  module: Module;
  kind: Kind;
  status: TaskStatus;
  version: number;
  params: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface TaskList {
  items: Task[];
}

export interface Candidate {
  id: string;
  task_id: string;
  label: string;
  starts_at: string | null;
  data: Record<string, unknown>;
  fit: number | null;
}

// Provisional frontend event contract.
export type BackendEvent =
  | { type: "assistant_message"; text: string }
  | { type: "progress"; task_id: string; step: number; note: string }
  | { type: "candidates"; task_id: string; candidates: Candidate[] }
  | { type: "status"; task_id: string; status: TaskStatus }
  | { type: "done"; task_id: string; summary: string };

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
}

export type Page = "chat" | "watches" | "settings";

export interface Watch {
  id: string;
  module: Module;
  title: string;
  description: string;
  active: boolean;
}

export interface UserPreferences {
  preferredTime: "morning" | "afternoon" | "evening" | "any";
  notificationChannel: "browser" | "email" | "both";
  calendarLinked: boolean;
}
