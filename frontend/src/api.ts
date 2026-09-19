export type EmailLabel =
  | "available"
  | "interview"
  | "assessment"
  | "rejected"
  | "applied"
  | "alert"
  | "others";

export type Provider = "google" | "microsoft";

export interface Mailbox {
  id: number;
  provider: Provider;
  email_address: string;
  display_name: string | null;
  is_active: boolean;
  created_at: string | null;
}

export interface EmailItem {
  id: number;
  mailbox_id: number;
  provider_message_id: string;
  subject: string;
  sender: string;
  received_at: string | null;
  snippet: string;
  label: EmailLabel;
  confidence: number | null;
  is_read: boolean;
  created_at: string | null;
}

export interface EmailDetail extends EmailItem {
  body_text: string;
  body_html?: string;
}

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

function friendlyNetworkError(err: unknown, fallback: string): Error {
  const message = err instanceof Error ? err.message : "";
  if (/failed to fetch|networkerror|load failed|econnrefused/i.test(message)) {
    return new Error("Cannot reach the API. Sync may still be running in the background — retry in a moment.");
  }
  return err instanceof Error ? err : new Error(fallback);
}

async function readApiError(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    if (Array.isArray(data?.detail)) {
      return data.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ") || fallback;
    }
  } catch {
    /* ignore */
  }
  return `${fallback} (${res.status})`;
}

async function apiFetch(url: string, init?: RequestInit, attempts = 3): Promise<Response> {
  let lastError: unknown = null;
  for (let i = 0; i < attempts; i += 1) {
    try {
      const res = await fetch(url, init);
      return res;
    } catch (err) {
      lastError = err;
      await new Promise((resolve) => window.setTimeout(resolve, 350 * (i + 1)));
    }
  }
  throw friendlyNetworkError(lastError, "Cannot reach the API");
}

export async function fetchMailboxes(): Promise<Mailbox[]> {
  const res = await apiFetch(`${API_BASE}/api/mailboxes`);
  if (!res.ok) throw new Error(await readApiError(res, "Failed to load mailboxes"));
  return res.json();
}

export interface EmailPage {
  items: EmailItem[];
  next_cursor: number | null;
  next_received_at: string | null;
  has_more: boolean;
  total: number;
  label_counts: Record<string, number>;
  mailbox_counts: Record<string, number>;
  mailbox_unread_counts: Record<string, number>;
}

export async function fetchEmails(opts?: {
  label?: string;
  mailboxId?: number | null;
  limit?: number;
  beforeId?: number | null;
  beforeReceivedAt?: string | null;
}): Promise<EmailPage> {
  const params = new URLSearchParams();
  if (opts?.label && opts.label !== "all") params.set("label", opts.label);
  if (opts?.mailboxId != null) params.set("mailbox_id", String(opts.mailboxId));
  params.set("limit", String(opts?.limit ?? 50));
  if (opts?.beforeId != null) params.set("before_id", String(opts.beforeId));
  if (opts?.beforeReceivedAt) params.set("before_received_at", opts.beforeReceivedAt);
  const qs = params.toString();
  const res = await apiFetch(`${API_BASE}/api/emails${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(await readApiError(res, "Failed to load emails"));
  return res.json();
}

export async function fetchEmailDetail(id: number): Promise<EmailDetail> {
  const res = await apiFetch(`${API_BASE}/api/emails/${id}`, undefined, 4);
  if (!res.ok) throw new Error(await readApiError(res, "Failed to load email"));
  return res.json();
}

export async function disconnectMailbox(id: number): Promise<void> {
  const res = await apiFetch(`${API_BASE}/api/mailboxes/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to disconnect mailbox");
}

export interface SyncStartResult {
  ok: boolean;
  state?: string;
  listed?: number;
  skipped?: number;
  imported?: number;
  failed?: number;
  total?: number;
  message?: string;
}

export async function syncMailbox(id: number): Promise<SyncStartResult> {
  const res = await apiFetch(`${API_BASE}/api/mailboxes/${id}/sync`, { method: "POST" });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to sync mailbox"));
  return res.json();
}

export async function reclassifyMailbox(id: number): Promise<{ updated: number; total: number }> {
  const res = await apiFetch(`${API_BASE}/api/mailboxes/${id}/reclassify`, { method: "POST" });
  if (!res.ok) throw new Error("Failed to reclassify mailbox");
  return res.json();
}

export function oauthStartUrl(
  provider: Provider,
  opts: { email: string; name?: string }
): string {
  const qs = new URLSearchParams({
    email: opts.email.trim(),
  });
  if (opts.name?.trim()) qs.set("name", opts.name.trim());
  return `${API_BASE}/api/auth/${provider}/start?${qs.toString()}`;
}

export function eventsUrl(): string {
  return `${API_BASE}/api/events`;
}
