export type EmailLabel =
  | "job_alert"
  | "applied"
  | "screening"
  | "interview"
  | "assessment"
  | "offer"
  | "rejected"
  | "others";

export type MailFolder = "inbox" | "spam" | "trash" | "archive";

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
  human_corrected?: boolean;
  folder?: MailFolder;
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
  next_is_read?: boolean | null;
  has_more: boolean;
  total: number;
  label_counts: Record<string, number>;
  mailbox_counts: Record<string, number>;
  mailbox_unread_counts: Record<string, number>;
  folder_counts?: Record<string, number>;
}

export async function fetchEmails(opts?: {
  label?: string;
  folder?: string;
  mailboxId?: number | null;
  query?: string | null;
  inboxType?: "default" | "unread_first";
  limit?: number;
  beforeId?: number | null;
  beforeReceivedAt?: string | null;
  beforeIsRead?: boolean | null;
}): Promise<EmailPage> {
  const params = new URLSearchParams();
  if (opts?.label && opts.label !== "all") params.set("label", opts.label);
  if (opts?.folder && opts.folder !== "all") params.set("folder", opts.folder);
  if (opts?.query?.trim()) params.set("q", opts.query.trim());
  if (opts?.mailboxId != null) params.set("mailbox_id", String(opts.mailboxId));
  if (opts?.inboxType && opts.inboxType !== "default") params.set("inbox_type", opts.inboxType);
  params.set("limit", String(opts?.limit ?? 50));
  if (opts?.beforeId != null) params.set("before_id", String(opts.beforeId));
  if (opts?.beforeReceivedAt) params.set("before_received_at", opts.beforeReceivedAt);
  if (opts?.beforeIsRead != null) params.set("before_is_read", String(opts.beforeIsRead));
  const qs = params.toString();
  const res = await apiFetch(`${API_BASE}/api/emails${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(await readApiError(res, "Failed to load emails"));
  return res.json();
}

export async function markAllRead(mailboxId?: number | null): Promise<{ marked: number }> {
  const params = new URLSearchParams();
  if (mailboxId != null) params.set("mailbox_id", String(mailboxId));
  const qs = params.toString();
  const res = await apiFetch(`${API_BASE}/api/emails/mark-all-read${qs ? `?${qs}` : ""}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to mark messages read"));
  return res.json();
}

export async function fetchEmailDetail(id: number): Promise<EmailDetail> {
  const res = await apiFetch(`${API_BASE}/api/emails/${id}`, undefined, 4);
  if (!res.ok) throw new Error(await readApiError(res, "Failed to load email"));
  return res.json();
}

export async function updateEmailLabel(
  id: number,
  label: EmailLabel,
  saveTraining: boolean
): Promise<EmailDetail> {
  const res = await apiFetch(`${API_BASE}/api/emails/${id}/label`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label, save_training: saveTraining }),
  });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to update category"));
  return res.json();
}

export interface ClassifyPromptStatus {
  unused_count: number;
  active_version_id: number | null;
  active_source: string | null;
  example_count: number;
  updated_at: string | null;
}

export interface ClassifyPromptUpdateResult {
  ok: boolean;
  example_count: number;
  prompt_version_id: number | null;
  message: string;
}

export async function fetchClassifyPromptStatus(): Promise<ClassifyPromptStatus> {
  const res = await apiFetch(`${API_BASE}/api/classify/prompt`);
  if (!res.ok) throw new Error(await readApiError(res, "Failed to load prompt status"));
  return res.json();
}

export async function updateClassifyPrompt(): Promise<ClassifyPromptUpdateResult> {
  const res = await apiFetch(`${API_BASE}/api/classify/prompt/update`, { method: "POST" });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to update classify prompt"));
  return res.json();
}

export interface ClassifyTrainingExample {
  id: number;
  email_id: number;
  previous_label: string;
  corrected_label: string;
  subject: string;
  sender: string;
  snippet: string;
  used_in_prompt_version_id: number | null;
  created_at: string | null;
}

export interface ClassifyTrainingPage {
  items: ClassifyTrainingExample[];
  unused_count: number;
  total: number;
}

export async function fetchClassifyTraining(opts?: {
  limit?: number;
  offset?: number;
}): Promise<ClassifyTrainingPage> {
  const params = new URLSearchParams();
  if (opts?.limit != null) params.set("limit", String(opts.limit));
  if (opts?.offset != null) params.set("offset", String(opts.offset));
  const qs = params.toString();
  const res = await apiFetch(`${API_BASE}/api/classify/training${qs ? `?${qs}` : ""}`);
  if (!res.ok) throw new Error(await readApiError(res, "Failed to load training data"));
  return res.json();
}

export interface MailboxLabelStats {
  mailbox_id: number | null;
  date_from: string;
  date_to: string;
  total: number;
  label_counts: Record<string, number>;
}

export interface LabelTimeline {
  mailbox_id: number;
  label: string;
  bucket: "hour" | "day";
  date_from: string;
  date_to: string;
  buckets: { bucket: string; count: number }[];
}

export interface OutcomeEntry {
  company: string;
  role: string;
  received_at: string | null;
  subject: string;
}

export interface MailboxOutcomes {
  mailbox_id: number;
  date_from: string;
  date_to: string;
  applied: OutcomeEntry[];
  rejected: OutcomeEntry[];
  screening: OutcomeEntry[];
  interview: OutcomeEntry[];
  items: OutcomeEntry[];
  total: number;
  label: string | null;
}

export type OutcomeLabel = "applied" | "rejected" | "screening" | "interview";

function statsRangeParams(dateFrom: string, dateTo: string): URLSearchParams {
  return new URLSearchParams({
    date_from: dateFrom,
    date_to: dateTo,
  });
}

export async function fetchMailboxLabelStats(
  mailboxId: number | "all",
  dateFrom: string,
  dateTo: string
): Promise<MailboxLabelStats> {
  const params = statsRangeParams(dateFrom, dateTo);
  const path = mailboxId === "all" ? "/api/mailboxes/label-stats" : `/api/mailboxes/${mailboxId}/label-stats`;
  const res = await apiFetch(`${API_BASE}${path}?${params}`);
  if (!res.ok) throw new Error(await readApiError(res, "Failed to load category statistics"));
  return res.json();
}

export async function fetchMailboxLabelTimeline(
  mailboxId: number,
  label: EmailLabel,
  dateFrom: string,
  dateTo: string
): Promise<LabelTimeline> {
  const params = statsRangeParams(dateFrom, dateTo);
  params.set("label", label);
  const res = await apiFetch(`${API_BASE}/api/mailboxes/${mailboxId}/label-timeline?${params}`);
  if (!res.ok) throw new Error(await readApiError(res, "Failed to load category timeline"));
  return res.json();
}

export async function fetchMailboxOutcomes(
  mailboxId: number,
  dateFrom: string,
  dateTo: string,
  page?: { label: OutcomeLabel; limit: number; offset: number }
): Promise<MailboxOutcomes> {
  const params = statsRangeParams(dateFrom, dateTo);
  if (page) {
    params.set("label", page.label);
    params.set("limit", String(page.limit));
    params.set("offset", String(page.offset));
  }
  const res = await apiFetch(`${API_BASE}/api/mailboxes/${mailboxId}/outcomes?${params}`);
  if (!res.ok) throw new Error(await readApiError(res, "Failed to load company and role lists"));
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

export async function reclassifyMailbox(id: number): Promise<SyncStartResult> {
  const res = await apiFetch(`${API_BASE}/api/mailboxes/${id}/reclassify`, { method: "POST" });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to reclassify mailbox"));
  return res.json();
}

export async function stopSyncMailbox(id: number): Promise<SyncStartResult> {
  const res = await apiFetch(`${API_BASE}/api/mailboxes/${id}/sync/stop`, { method: "POST" });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to stop sync"));
  return res.json();
}

export async function stopReclassifyMailbox(id: number): Promise<SyncStartResult> {
  const res = await apiFetch(`${API_BASE}/api/mailboxes/${id}/reclassify/stop`, { method: "POST" });
  if (!res.ok) throw new Error(await readApiError(res, "Failed to stop reclassify"));
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
