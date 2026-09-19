import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import EmailBody from "./components/EmailBody";
import {
  disconnectMailbox,
  eventsUrl,
  fetchEmailDetail,
  fetchEmails,
  fetchMailboxes,
  oauthStartUrl,
  syncMailbox,
  reclassifyMailbox,
  type EmailDetail,
  type EmailItem,
  type EmailLabel,
  type EmailPage,
  type Mailbox,
  type Provider,
} from "./api";

const PAGE_SIZE = 50;

const CLASSIFY_LABELS: EmailLabel[] = [
  "available",
  "interview",
  "assessment",
  "rejected",
  "applied",
  "alert",
  "others",
];

const EMPTY_LABEL_COUNTS: Record<EmailLabel, number> = {
  available: 0,
  interview: 0,
  assessment: 0,
  rejected: 0,
  applied: 0,
  alert: 0,
  others: 0,
};

function parseLabelCounts(raw: Record<string, number>): Record<EmailLabel, number> {
  const counts = { ...EMPTY_LABEL_COUNTS };
  for (const key of CLASSIFY_LABELS) {
    counts[key] = raw[key] ?? 0;
  }
  return counts;
}

function parseMailboxCounts(raw: Record<string, number>): Record<number, number> {
  const out: Record<number, number> = {};
  for (const [key, value] of Object.entries(raw)) {
    const id = Number(key);
    if (!Number.isNaN(id)) out[id] = value;
  }
  return out;
}

function parseApiDate(value: string | null): Date | null {
  if (!value) return null;
  const hasZone = /Z$/i.test(value) || /[+-]\d{2}:\d{2}$/.test(value);
  const d = new Date(hasZone ? value : `${value}Z`);
  return Number.isNaN(d.getTime()) ? null : d;
}

function localDateKey(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function formatDateHeading(key: string): string {
  const [y, m, d] = key.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  const today = startOfDay(new Date());
  const diffDays = Math.round((today.getTime() - startOfDay(date).getTime()) / 86_400_000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  return new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "short",
    day: "numeric",
  }).format(date);
}

function formatItemTimeAndDay(value: string | null): { time: string; day: string } {
  const d = parseApiDate(value);
  if (!d) return { time: "", day: "" };
  return {
    time: new Intl.DateTimeFormat(undefined, {
      hour: "numeric",
      minute: "2-digit",
    }).format(d),
    day: new Intl.DateTimeFormat(undefined, { weekday: "short" }).format(d),
  };
}

function formatReaderTime(value: string | null): string {
  const d = parseApiDate(value);
  if (!d) return "";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(d);
}

function senderName(sender: string): string {
  const match = sender.match(/^"?([^"<]+)"?\s*</);
  if (match?.[1]) return match[1].trim();
  return sender || "Unknown";
}

function initialsFrom(text: string): string {
  const clean = text.replace(/@.*/, "").replace(/[^a-zA-Z0-9 ]/g, " ").trim();
  const parts = clean.split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

function providerMark(provider: Provider): string {
  return provider === "google" ? "G" : "O";
}

export default function App() {
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [emails, setEmails] = useState<EmailItem[]>([]);
  const [selectedMailboxId, setSelectedMailboxId] = useState<number | null>(null);
  const [label, setLabel] = useState<"all" | EmailLabel>("all");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<number | null>(null);
  const [nextReceivedAt, setNextReceivedAt] = useState<string | null>(null);
  const [labelCounts, setLabelCounts] = useState<Record<EmailLabel, number>>(EMPTY_LABEL_COUNTS);
  const [mailboxCounts, setMailboxCounts] = useState<Record<number, number>>({});
  const [mailboxUnreadCounts, setMailboxUnreadCounts] = useState<Record<number, number>>({});
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  const [connectEmail, setConnectEmail] = useState("");
  const [connectProvider, setConnectProvider] = useState<Provider>("google");
  const [addAccountOpen, setAddAccountOpen] = useState(false);
  const [dialogStep, setDialogStep] = useState<"type" | "email">("type");
  const [syncingId, setSyncingId] = useState<number | null>(null);
  const [reclassifyingId, setReclassifyingId] = useState<number | null>(null);
  const [actionStatus, setActionStatus] = useState<{
    type: "sync" | "reclassify" | "success" | "error";
    message: string;
  } | null>(null);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selected, setSelected] = useState<EmailDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [collapsedDates, setCollapsedDates] = useState<Set<string>>(new Set());

  const filterRef = useRef({ mailboxId: selectedMailboxId, label });
  filterRef.current = { mailboxId: selectedMailboxId, label };
  const fetchGen = useRef(0);
  const loadingMoreRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const didMountFilters = useRef(false);

  const applyPageMeta = useCallback((page: EmailPage) => {
    setHasMore(page.has_more);
    setNextCursor(page.next_cursor);
    setNextReceivedAt(page.next_received_at ?? null);
    setLabelCounts(parseLabelCounts(page.label_counts));
    setMailboxCounts(parseMailboxCounts(page.mailbox_counts));
    setMailboxUnreadCounts(parseMailboxCounts(page.mailbox_unread_counts ?? {}));
  }, []);

  const loadFirstPage = useCallback(async () => {
    const gen = ++fetchGen.current;
    const { mailboxId, label: currentLabel } = filterRef.current;
    setLoading(true);
    setLoadingMore(false);
    loadingMoreRef.current = false;
    setError(null);
    setHasMore(false);
    setNextCursor(null);
    setNextReceivedAt(null);
    try {
      const page = await fetchEmails({
        mailboxId,
        label: currentLabel,
        limit: PAGE_SIZE,
      });
      if (gen !== fetchGen.current) return;
      setEmails(page.items);
      applyPageMeta(page);
    } catch (err) {
      if (gen !== fetchGen.current) return;
      setError(err instanceof Error ? err.message : "Failed to load emails");
      setEmails([]);
    } finally {
      if (gen === fetchGen.current) setLoading(false);
    }
  }, [applyPageMeta]);

  const loadMore = useCallback(async () => {
    if (loadingMoreRef.current || !hasMore || nextCursor == null) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    const gen = fetchGen.current;
    const { mailboxId, label: currentLabel } = filterRef.current;
    try {
      const page = await fetchEmails({
        mailboxId,
        label: currentLabel,
        limit: PAGE_SIZE,
        beforeId: nextCursor,
        beforeReceivedAt: nextReceivedAt,
      });
      if (gen !== fetchGen.current) return;
      setEmails((prev) => {
        const seen = new Set(prev.map((item) => item.id));
        const extra = page.items.filter((item) => !seen.has(item.id));
        return extra.length ? [...prev, ...extra] : prev;
      });
      applyPageMeta(page);
    } catch (err) {
      if (gen !== fetchGen.current) return;
      setError(err instanceof Error ? err.message : "Failed to load emails");
    } finally {
      loadingMoreRef.current = false;
      if (gen === fetchGen.current) setLoadingMore(false);
    }
  }, [applyPageMeta, hasMore, nextCursor, nextReceivedAt]);

  const load = useCallback(async () => {
    setError(null);
    try {
      const boxes = await fetchMailboxes();
      setMailboxes(boxes);
      const current = filterRef.current.mailboxId;
      const nextId = current != null && !boxes.some((b) => b.id === current) ? null : current;
      filterRef.current = { ...filterRef.current, mailboxId: nextId };
      setSelectedMailboxId(nextId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load mailboxes");
      setLoading(false);
      return;
    }
    await loadFirstPage();
  }, [loadFirstPage]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const oauth = params.get("oauth");
    if (oauth === "ok") {
      const name = params.get("name");
      const email = params.get("email");
      setBanner(
        `Connected ${params.get("provider") ?? "mailbox"}: ${name ? `${name} <${email}>` : email}`
      );
      window.history.replaceState({}, "", "/");
    } else if (oauth === "error") {
      setBanner(`OAuth error: ${params.get("detail") ?? "unknown"}`);
      window.history.replaceState({}, "", "/");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!didMountFilters.current) {
      didMountFilters.current = true;
      return;
    }
    setEmails([]);
    scrollRef.current?.scrollTo(0, 0);
    void loadFirstPage();
  }, [selectedMailboxId, label, loadFirstPage]);

  useEffect(() => {
    const source = new EventSource(eventsUrl());
    source.addEventListener("connected", () => setLive(true));
    source.addEventListener("email.classified", (evt) => {
      try {
        const item = JSON.parse((evt as MessageEvent).data) as EmailItem;
        const { mailboxId, label: currentLabel } = filterRef.current;
        const matchesMailbox = mailboxId == null || item.mailbox_id === mailboxId;
        const matchesLabel = currentLabel === "all" || item.label === currentLabel;
        if (matchesMailbox && matchesLabel) {
          setEmails((prev) => {
            if (prev.some((e) => e.id === item.id)) return prev;
            return [{ ...item, is_read: Boolean(item.is_read) }, ...prev];
          });
        }
        setMailboxCounts((prev) => ({
          ...prev,
          [item.mailbox_id]: (prev[item.mailbox_id] ?? 0) + 1,
        }));
        if (!item.is_read) {
          setMailboxUnreadCounts((prev) => ({
            ...prev,
            [item.mailbox_id]: (prev[item.mailbox_id] ?? 0) + 1,
          }));
        }
        if (matchesMailbox) {
          setLabelCounts((prev) => ({
            ...prev,
            [item.label]: (prev[item.label] ?? 0) + 1,
          }));
        }
      } catch {
        /* ignore */
      }
    });
    source.addEventListener("sync.progress", (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data) as {
          message?: string;
          imported?: number;
          total?: number;
        };
        const imported = data.imported ?? 0;
        const total = data.total ?? 0;
        setActionStatus({
          type: "sync",
          message: data.message || `Syncing… ${imported}${total ? ` / ${total}` : ""}`,
        });
      } catch {
        /* ignore */
      }
    });
    source.addEventListener("sync.done", (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data) as {
          state?: string;
          message?: string;
          imported?: number;
        };
        void load();
        setSyncingId(null);
        if (data.state === "error") {
          setActionStatus({ type: "error", message: data.message || "Sync failed" });
        } else {
          setActionStatus({
            type: "success",
            message: data.message || `Sync complete${data.imported != null ? ` — ${data.imported} new` : ""}`,
          });
          window.setTimeout(() => setActionStatus(null), 4000);
        }
      } catch {
        void load();
      }
    });
    source.onerror = () => setLive(false);
    return () => source.close();
  }, [load]);

  const mailboxById = useMemo(() => {
    const map = new Map<number, Mailbox>();
    for (const box of mailboxes) map.set(box.id, box);
    return map;
  }, [mailboxes]);

  const inboxCount = useMemo(
    () => Object.values(mailboxCounts).reduce((sum, n) => sum + n, 0),
    [mailboxCounts]
  );

  const allCount = useMemo(
    () => CLASSIFY_LABELS.reduce((sum, key) => sum + (labelCounts[key] ?? 0), 0),
    [labelCounts]
  );

  const dateGroups = useMemo(() => {
    const buckets = new Map<string, EmailItem[]>();
    for (const email of emails) {
      let key = "unknown";
      if (email.received_at) {
        try {
          const received = parseApiDate(email.received_at);
          if (received) key = localDateKey(received);
        } catch {
          key = "unknown";
        }
      }
      const list = buckets.get(key);
      if (list) list.push(email);
      else buckets.set(key, [email]);
    }
    return [...buckets.entries()]
      .sort(([a], [b]) => (a === "unknown" ? 1 : b === "unknown" ? -1 : b.localeCompare(a)))
      .map(([key, items]) => ({
        key,
        heading: key === "unknown" ? "Unknown date" : formatDateHeading(key),
        items,
      }));
  }, [emails]);

  useEffect(() => {
    const root = scrollRef.current;
    const sentinel = sentinelRef.current;
    if (!root || !sentinel) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) void loadMore();
      },
      { root, rootMargin: "160px" }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadMore, emails.length, loading]);

  function toggleDateGroup(key: string) {
    setCollapsedDates((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function openAddAccount() {
    setConnectEmail("");
    setConnectProvider("google");
    setDialogStep("type");
    setAddAccountOpen(true);
  }

  function closeAddAccount() {
    setAddAccountOpen(false);
    setDialogStep("type");
    setConnectEmail("");
  }

  function chooseAccountType(provider: Provider) {
    setConnectProvider(provider);
    setDialogStep("email");
  }

  function guessProviderFromEmail(email: string): Provider | null {
    const domain = email.trim().toLowerCase().split("@")[1] ?? "";
    if (["gmail.com", "googlemail.com"].includes(domain)) return "google";
    if (["outlook.com", "hotmail.com", "live.com", "msn.com", "office365.com"].includes(domain)) {
      return "microsoft";
    }
    return null;
  }

  function connectWithEmail() {
    const email = connectEmail.trim();
    if (!email || !email.includes("@")) {
      setBanner("Enter a valid email address.");
      return;
    }
    const guessed = guessProviderFromEmail(email);
    const provider = guessed ?? connectProvider;
    window.location.href = oauthStartUrl(provider, { email });
  }

  function onConnectEmailSubmit(e: FormEvent) {
    e.preventDefault();
    connectWithEmail();
  }

  async function onDisconnect(id: number) {
    await disconnectMailbox(id);
    if (selected?.mailbox_id === id) {
      setSelected(null);
      setSelectedId(null);
    }
    if (selectedMailboxId === id) setSelectedMailboxId(null);
    await load();
  }

  async function onSync(id: number) {
    const box = mailboxById.get(id);
    const name = box?.email_address ?? "mailbox";
    setSyncingId(id);
    setActionStatus({ type: "sync", message: `Syncing ${name}… listing Inbox` });
    try {
      const started = await syncMailbox(id);
      setActionStatus({
        type: "sync",
        message: started.message || `Syncing ${name} in the background…`,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Sync failed";
      setActionStatus({ type: "error", message: msg });
      setSyncingId(null);
    }
  }

  async function onReclassify(id: number) {
    const box = mailboxById.get(id);
    const name = box?.email_address ?? "mailbox";
    setReclassifyingId(id);
    setActionStatus({
      type: "reclassify",
      message: `Reclassifying ${name}… running AI labels`,
    });
    try {
      const result = await reclassifyMailbox(id);
      await load();
      setActionStatus({
        type: "success",
        message: `Reclassify complete — updated ${result.updated} of ${result.total} emails`,
      });
      window.setTimeout(() => setActionStatus(null), 4000);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Reclassify failed";
      setActionStatus({ type: "error", message: msg });
    } finally {
      setReclassifyingId(null);
    }
  }

  async function onOpenEmail(id: number) {
    setSelectedId(id);
    setLoadingDetail(true);
    try {
      const detail = await fetchEmailDetail(id);
      setSelected(detail);
      setEmails((prev) => {
        const opened = prev.find((item) => item.id === id);
        if (opened && !opened.is_read) {
          setMailboxUnreadCounts((counts) => ({
            ...counts,
            [opened.mailbox_id]: Math.max(0, (counts[opened.mailbox_id] ?? 1) - 1),
          }));
        }
        return prev.map((item) => (item.id === id ? { ...item, is_read: true } : item));
      });
    } catch (err) {
      setBanner(err instanceof Error ? err.message : "Could not open email");
    } finally {
      setLoadingDetail(false);
    }
  }

  function selectMailbox(id: number | null) {
    scrollRef.current?.scrollTo(0, 0);
    if (selectedMailboxId === id) {
      setEmails([]);
      void loadFirstPage();
      return;
    }
    setSelectedMailboxId(id);
  }

  function selectLabel(next: "all" | EmailLabel) {
    scrollRef.current?.scrollTo(0, 0);
    if (label === next) {
      setEmails([]);
      void loadFirstPage();
      return;
    }
    setLabel(next);
  }

  const selectedMailbox = selectedMailboxId != null ? mailboxById.get(selectedMailboxId) : null;
  const readerTo =
    selected != null
      ? mailboxById.get(selected.mailbox_id)?.email_address ?? ""
      : "";

  return (
    <div className="app-shell">
      <aside className="pane-accounts">
        <div className="accounts-top">
          <div className="brand-mini">Auto AI Email Checker</div>
          <div className="live-mini" data-live={live}>
            <span className="dot" />
            {live ? "Live" : "…"}
          </div>
        </div>

        <button
          type="button"
          className={selectedMailboxId == null ? "nav-inbox active" : "nav-inbox"}
          onClick={() => selectMailbox(null)}
        >
          <span className="nav-inbox-icon" aria-hidden="true">
            ▣
          </span>
          <span>Inbox</span>
          <span className="nav-count">{inboxCount}</span>
        </button>

        <div className="accounts-label">Accounts</div>
        <div className="accounts-scroll">
          {mailboxes.map((box) => {
            const count = mailboxCounts[box.id] ?? 0;
            const unread = mailboxUnreadCounts[box.id] ?? 0;
            return (
              <div key={box.id} className="account-row-wrap">
                <button
                  type="button"
                  className={
                    selectedMailboxId === box.id ? "account-row active" : "account-row"
                  }
                  onClick={() => selectMailbox(box.id)}
                  title={box.email_address}
                >
                  <span className={`avatar provider-${box.provider}`}>
                    {providerMark(box.provider)}
                  </span>
                  <span className="account-main">
                    <span className="account-email">{box.email_address}</span>
                    {unread > 0 ? (
                      <span className="account-new-badge" title={`${unread} new messages`}>
                        NEW {unread}
                      </span>
                    ) : (
                      <span className="account-total">{count}</span>
                    )}
                  </span>
                </button>
                <div className="account-row-actions">
                  <button
                    type="button"
                    className={syncingId === box.id ? "action-btn busy" : "action-btn"}
                    disabled={syncingId === box.id || reclassifyingId === box.id}
                    onClick={() => void onSync(box.id)}
                  >
                    {syncingId === box.id ? (
                      <>
                        <span className="spinner" aria-hidden="true" />
                        Syncing…
                      </>
                    ) : (
                      "Sync"
                    )}
                  </button>
                  <button
                    type="button"
                    className={reclassifyingId === box.id ? "action-btn busy" : "action-btn"}
                    disabled={syncingId === box.id || reclassifyingId === box.id}
                    onClick={() => void onReclassify(box.id)}
                  >
                    {reclassifyingId === box.id ? (
                      <>
                        <span className="spinner" aria-hidden="true" />
                        Reclassifying…
                      </>
                    ) : (
                      "Reclassify"
                    )}
                  </button>
                  <button
                    type="button"
                    className="action-btn danger"
                    disabled={syncingId === box.id || reclassifyingId === box.id}
                    onClick={() => void onDisconnect(box.id)}
                  >
                    Remove
                  </button>
                </div>
                {(syncingId === box.id || reclassifyingId === box.id) && (
                  <div className="account-progress" role="status">
                    <span className="spinner" aria-hidden="true" />
                    {syncingId === box.id ? "Sync in progress…" : "Reclassify in progress…"}
                  </div>
                )}
              </div>
            );
          })}
          {!mailboxes.length && <p className="hint">No accounts yet</p>}
        </div>

        <button type="button" className="add-account-btn" onClick={openAddAccount}>
          + Add an account
        </button>
      </aside>

      <section className="pane-list">
        <header className="list-header">
          <div className="list-title">
            <span className="view-chip">Inbox View</span>
            <h2>
              {selectedMailbox ? selectedMailbox.email_address : "All accounts"}
            </h2>
          </div>
          <div className="classify-badges" role="tablist" aria-label="Classifications">
            <button
              type="button"
              className={label === "all" ? "classify-badge active" : "classify-badge"}
              onClick={() => selectLabel("all")}
            >
              all
              <span className="count-pill">{allCount}</span>
            </button>
            {CLASSIFY_LABELS.map((item) => (
              <button
                key={item}
                type="button"
                className={
                  label === item ? `classify-badge active label-${item}` : `classify-badge label-${item}`
                }
                onClick={() => selectLabel(item)}
              >
                {item}
                <span className="count-pill">{labelCounts[item]}</span>
              </button>
            ))}
          </div>
        </header>

        {actionStatus && (
          <div className={`action-toast ${actionStatus.type}`} role="status">
            {(actionStatus.type === "sync" || actionStatus.type === "reclassify") && (
              <span className="spinner" aria-hidden="true" />
            )}
            <span>{actionStatus.message}</span>
            {(actionStatus.type === "success" || actionStatus.type === "error") && (
              <button type="button" onClick={() => setActionStatus(null)}>
                Dismiss
              </button>
            )}
          </div>
        )}

        {banner && (
          <div className="banner inline" role="status">
            <span>{banner}</span>
            <button type="button" onClick={() => setBanner(null)}>
              Dismiss
            </button>
          </div>
        )}
        {loading && <p className="hint pad">Loading…</p>}
        {error && <p className="error pad">{error}</p>}

        <div className="message-scroll" ref={scrollRef}>
          {!loading &&
            dateGroups.map((group) => {
              const collapsed = collapsedDates.has(group.key);
              return (
                <div key={group.key} className={collapsed ? "msg-group collapsed" : "msg-group"}>
                  <button
                    type="button"
                    className="msg-group-head"
                    onClick={() => toggleDateGroup(group.key)}
                    aria-expanded={!collapsed}
                  >
                    <span className="date-chevron" aria-hidden="true">
                      {collapsed ? "▸" : "▾"}
                    </span>
                    <span className="date-heading">{group.heading}</span>
                    <span className="group-count">{group.items.length}</span>
                  </button>
                  {!collapsed &&
                    group.items.map((email) => {
                      const when = formatItemTimeAndDay(email.received_at);
                      return (
                        <button
                          key={email.id}
                          type="button"
                          className={
                            selectedId === email.id
                              ? "msg-item active"
                              : email.is_read
                                ? "msg-item"
                                : "msg-item unread"
                          }
                          onClick={() => void onOpenEmail(email.id)}
                        >
                          <span className={`avatar soft label-${email.label}`}>
                            {initialsFrom(senderName(email.sender))}
                          </span>
                          <span className="msg-body">
                            <span className="msg-top">
                              <strong>{senderName(email.sender)}</strong>
                              <span className="msg-meta">
                                <span className={email.is_read ? "read-pill" : "new-pill"}>
                                  {email.is_read ? "Read" : "NEW"}
                                </span>
                                <time>
                                  <span className="msg-time">{when.time}</span>
                                  {when.day && <span className="msg-day">{when.day}</span>}
                                </time>
                              </span>
                            </span>
                            <span className="msg-subject">{email.subject || "(no subject)"}</span>
                            <span className="msg-snippet">{email.snippet}</span>
                          </span>
                        </button>
                      );
                    })}
                </div>
              );
            })}
          {!loading && !emails.length && mailboxes.length > 0 && (
            <p className="hint pad">No classified emails yet. Sync an account.</p>
          )}
          {!loading && !mailboxes.length && (
            <p className="hint pad">Add an account to start.</p>
          )}
          <div ref={sentinelRef} className="scroll-sentinel" aria-hidden="true" />
          {loadingMore && <p className="hint pad loading-more">Loading more…</p>}
        </div>
      </section>

      <section className="pane-reader">
        {!selected && !loadingDetail && (
          <div className="reader-empty">
            <p>Select a message to read</p>
          </div>
        )}
        {loadingDetail && <div className="reader-empty"><p>Opening…</p></div>}
        {selected && !loadingDetail && (
          <article className="reader-article">
            <h1>{selected.subject || "(no subject)"}</h1>
            <div className="reader-card">
              <div className="reader-meta">
                <div className="reader-people">
                  <span className={`avatar soft label-${selected.label}`}>
                    {initialsFrom(senderName(selected.sender))}
                  </span>
                  <div>
                    <strong>{selected.sender || senderName(selected.sender)}</strong>
                    <p>
                      to <span className="to-address">{readerTo || "me"}</span>
                    </p>
                  </div>
                </div>
                <div className="reader-side">
                  <span className={`label label-${selected.label}`}>{selected.label}</span>
                  <time>{formatReaderTime(selected.received_at)}</time>
                </div>
              </div>
              <EmailBody
                html={selected.body_html}
                text={selected.body_text}
                snippet={selected.snippet}
              />
            </div>
          </article>
        )}
      </section>

      {addAccountOpen && (
        <div
          className="dialog-backdrop"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeAddAccount();
          }}
        >
          <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="add-account-title">
            <header className="dialog-header">
              <h3 id="add-account-title">Add an account</h3>
              <button type="button" className="dialog-close" onClick={closeAddAccount} aria-label="Close">
                ×
              </button>
            </header>
            {dialogStep === "type" ? (
              <div className="dialog-body">
                <p className="dialog-hint">Choose your email type</p>
                <div className="account-type-grid">
                  <button
                    type="button"
                    className="account-type gmail"
                    onClick={() => chooseAccountType("google")}
                  >
                    <span className="account-type-name">Gmail</span>
                    <span className="account-type-sub">Google account</span>
                  </button>
                  <button
                    type="button"
                    className="account-type outlook"
                    onClick={() => chooseAccountType("microsoft")}
                  >
                    <span className="account-type-name">Outlook</span>
                    <span className="account-type-sub">Microsoft account</span>
                  </button>
                </div>
              </div>
            ) : (
              <form className="dialog-body" onSubmit={onConnectEmailSubmit}>
                <button type="button" className="text-btn back-link" onClick={() => setDialogStep("type")}>
                  ← {connectProvider === "google" ? "Gmail" : "Outlook"}
                </button>
                <p className="dialog-hint">
                  Enter your email, then press Enter to connect.
                </p>
                <label className="dialog-email-label">
                  Email
                  <input
                    type="email"
                    value={connectEmail}
                    onChange={(e) => setConnectEmail(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "ArrowDown" && connectEmail.includes("@")) {
                        e.preventDefault();
                        connectWithEmail();
                      }
                    }}
                    placeholder={
                      connectProvider === "google" ? "name@gmail.com" : "name@outlook.com"
                    }
                    required
                    autoFocus
                    autoComplete="email"
                  />
                </label>
                <button
                  type="submit"
                  className={`primary-btn ${connectProvider === "google" ? "google" : "outlook"}`}
                >
                  Connect
                </button>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
