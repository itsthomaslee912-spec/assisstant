import { CSSProperties, Dispatch, FormEvent, PointerEvent, SetStateAction, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import EmailBody from "./components/EmailBody";
import MessageRow from "./components/MessageRow";
import SettingsPage, { type SettingsSection } from "./pages/SettingsPage";
import {
  disconnectMailbox,
  eventsUrl,
  fetchClassifyPromptStatus,
  fetchEmailDetail,
  fetchEmails,
  fetchMailboxes,
  oauthStartUrl,
  syncMailbox,
  reclassifyMailbox,
  stopSyncMailbox,
  stopReclassifyMailbox,
  updateClassifyPrompt,
  updateEmailLabel,
  type EmailDetail,
  type EmailItem,
  type EmailLabel,
  type EmailPage,
  type MailFolder,
  type Mailbox,
  type Provider,
} from "./api";
import { CLASSIFY_LABELS, CLASSIFY_LABEL_TITLES, EMPTY_LABEL_COUNTS } from "./labels";
import {
  applyFontFamily,
  applyFontSize,
  loadFontFamily,
  loadFontSize,
  loadViewMode,
  saveFontFamily,
  saveFontSize,
  saveViewMode,
  VIEW_MODES,
  type FontFamily,
  type FontSize,
  type ViewMode,
} from "./prefs";
import { applyTheme, loadThemePref, saveThemePref, type ThemePref } from "./theme";

const PAGE_SIZE = 50;
const LIST_OVERSCAN = 12;
const LIST_ROW_GROUP_H = 40;
const LIST_ROW_EMAIL_H = 102;
const LIST_ROW_TABLE_H = 44;
const LIST_ROW_CARD_H = 148;

type ListRow =
  | { kind: "group"; key: string; heading: string; count: number }
  | { kind: "email"; email: EmailItem };

const ACCOUNTS_MIN = 180;
const LIST_MIN = 240;
const READER_MIN = 280;
const ACCOUNTS_W_KEY = "email-checker-accounts-w";
const LIST_W_KEY = "email-checker-list-w";

function loadStoredWidth(key: string, fallback: number, min: number): number {
  try {
    const n = Number(localStorage.getItem(key));
    if (Number.isFinite(n) && n >= min) return Math.round(n);
  } catch {
    /* ignore */
  }
  return fallback;
}

const MAIL_FOLDERS: MailFolder[] = ["inbox", "spam", "trash", "archive"];
const MAIL_FOLDER_TITLES: Record<MailFolder, string> = {
  inbox: "Inbox",
  spam: "Spam",
  trash: "Trash",
  archive: "Archive",
};
const EMPTY_FOLDER_COUNTS: Record<MailFolder, number> = {
  inbox: 0,
  spam: 0,
  trash: 0,
  archive: 0,
};

function parseFolderCounts(raw: Record<string, number> | undefined): Record<MailFolder, number> {
  const counts = { ...EMPTY_FOLDER_COUNTS };
  for (const key of MAIL_FOLDERS) {
    counts[key] = raw?.[key] ?? 0;
  }
  return counts;
}

function mailFolderOf(email: { folder?: MailFolder | string | null }): MailFolder {
  const value = email.folder;
  return MAIL_FOLDERS.includes(value as MailFolder) ? (value as MailFolder) : "inbox";
}

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

function emailRowHeight(mode: ViewMode): number {
  if (mode === "table") return LIST_ROW_TABLE_H;
  if (mode === "card") return LIST_ROW_CARD_H;
  return LIST_ROW_EMAIL_H;
}

function providerMark(provider: Provider): string {
  return provider === "google" ? "G" : "O";
}

export default function App() {
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [emails, setEmails] = useState<EmailItem[]>([]);
  const [selectedMailboxId, setSelectedMailboxId] = useState<number | null>(null);
  const [label, setLabel] = useState<"all" | EmailLabel>("all");
  const [folder, setFolder] = useState<"all" | MailFolder>("all");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<number | null>(null);
  const [nextReceivedAt, setNextReceivedAt] = useState<string | null>(null);
  const [labelCounts, setLabelCounts] = useState<Record<EmailLabel, number>>(EMPTY_LABEL_COUNTS);
  const [mailboxCounts, setMailboxCounts] = useState<Record<number, number>>({});
  const [mailboxUnreadCounts, setMailboxUnreadCounts] = useState<Record<number, number>>({});
  const [folderCounts, setFolderCounts] = useState<Record<MailFolder, number>>(EMPTY_FOLDER_COUNTS);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  const [connectEmail, setConnectEmail] = useState("");
  const [connectProvider, setConnectProvider] = useState<Provider>("google");
  const [addAccountOpen, setAddAccountOpen] = useState(false);
  const [dialogStep, setDialogStep] = useState<"type" | "email">("type");
  const [syncingIds, setSyncingIds] = useState<Set<number>>(() => new Set());
  const [reclassifyingIds, setReclassifyingIds] = useState<Set<number>>(() => new Set());
  const [actionStatus, setActionStatus] = useState<{
    type: "sync" | "reclassify" | "success" | "error";
    message: string;
  } | null>(null);
  const [saveTraining, setSaveTraining] = useState(false);
  const [savingLabel, setSavingLabel] = useState(false);
  const [unusedTraining, setUnusedTraining] = useState(0);
  const [updatingPrompt, setUpdatingPrompt] = useState(false);
  const [pendingLabel, setPendingLabel] = useState<{ emailId: number; nextLabel: EmailLabel } | null>(
    null
  );

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selected, setSelected] = useState<EmailDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [collapsedDates, setCollapsedDates] = useState<Set<string>>(new Set());
  const [accountsW, setAccountsW] = useState(() => loadStoredWidth(ACCOUNTS_W_KEY, 260, ACCOUNTS_MIN));
  const [listW, setListW] = useState(() => loadStoredWidth(LIST_W_KEY, 360, LIST_MIN));
  const [themePref, setThemePref] = useState<ThemePref>(() => loadThemePref());
  const [viewMode, setViewMode] = useState<ViewMode>(() => loadViewMode());
  const [fontFamily, setFontFamily] = useState<FontFamily>(() => loadFontFamily());
  const [fontSize, setFontSize] = useState<FontSize>(() => loadFontSize());
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsSection, setSettingsSection] = useState<SettingsSection>("appearance");
  const [resizing, setResizing] = useState(false);

  const filterRef = useRef({ mailboxId: selectedMailboxId, label, folder });
  filterRef.current = { mailboxId: selectedMailboxId, label, folder };
  const fetchGen = useRef(0);
  const loadingMoreRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const didMountFilters = useRef(false);
  const shellRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{
    which: "accounts" | "list";
    startX: number;
    startAccounts: number;
    startList: number;
  } | null>(null);
  const widthsRef = useRef({ accounts: accountsW, list: listW });
  widthsRef.current = { accounts: accountsW, list: listW };
  const mailboxesRef = useRef(mailboxes);
  mailboxesRef.current = mailboxes;
  const syncingIdsRef = useRef(syncingIds);
  syncingIdsRef.current = syncingIds;
  const reclassifyingIdsRef = useRef(reclassifyingIds);
  reclassifyingIdsRef.current = reclassifyingIds;

  function accountName(id?: number | null): string {
    if (id == null) return "";
    return mailboxesRef.current.find((box) => box.id === id)?.email_address ?? "";
  }

  function withAccount(id: number | null | undefined, message: string): string {
    const name = accountName(id);
    return name ? `${name} — ${message}` : message;
  }

  function setIdInSet(
    setter: Dispatch<SetStateAction<Set<number>>>,
    id: number,
    present: boolean,
  ) {
    setter((prev) => {
      const next = new Set(prev);
      if (present) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  const applyPageMeta = useCallback((page: EmailPage) => {
    setHasMore(page.has_more);
    setNextCursor(page.next_cursor);
    setNextReceivedAt(page.next_received_at ?? null);
    setLabelCounts(parseLabelCounts(page.label_counts));
    setMailboxCounts(parseMailboxCounts(page.mailbox_counts));
    setMailboxUnreadCounts(parseMailboxCounts(page.mailbox_unread_counts ?? {}));
    setFolderCounts(parseFolderCounts(page.folder_counts));
  }, []);

  const loadFirstPage = useCallback(async () => {
    const gen = ++fetchGen.current;
    const { mailboxId, label: currentLabel, folder: currentFolder } = filterRef.current;
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
        folder: currentFolder,
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
    const { mailboxId, label: currentLabel, folder: currentFolder } = filterRef.current;
    try {
      const page = await fetchEmails({
        mailboxId,
        label: currentLabel,
        folder: currentFolder,
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

  const refreshPromptStatus = useCallback(async () => {
    try {
      const status = await fetchClassifyPromptStatus();
      setUnusedTraining(status.unused_count);
    } catch {
      /* ignore */
    }
  }, []);

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
    await Promise.all([loadFirstPage(), refreshPromptStatus()]);
  }, [loadFirstPage, refreshPromptStatus]);

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
  }, [selectedMailboxId, label, folder, loadFirstPage]);

  useEffect(() => {
    const source = new EventSource(eventsUrl());
    source.addEventListener("connected", () => setLive(true));
    source.addEventListener("mailbox.disconnected", (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data) as { mailbox_id?: number };
        const id = data.mailbox_id;
        if (id != null) {
          setEmails((prev) => prev.filter((e) => e.mailbox_id !== id));
          setSelected((prev) => (prev && prev.mailbox_id === id ? null : prev));
        }
      } catch {
        /* ignore */
      }
      void load();
    });
    source.addEventListener("email.classified", (evt) => {
      try {
        const item = JSON.parse((evt as MessageEvent).data) as EmailItem & {
          previous_label?: EmailLabel;
          updated?: boolean;
        };
        const { mailboxId, label: currentLabel, folder: currentFolder } = filterRef.current;
        const matchesMailbox = mailboxId == null || item.mailbox_id === mailboxId;
        const matchesLabel = currentLabel === "all" || item.label === currentLabel;
        const itemFolder = mailFolderOf(item);
        const matchesFolder = currentFolder === "all" || itemFolder === currentFolder;
        const isUpdate = Boolean(item.updated);

        setEmails((prev) => {
          const existingIdx = prev.findIndex((e) => e.id === item.id);
          if (existingIdx >= 0) {
            if (matchesMailbox && matchesLabel && matchesFolder) {
              const next = [...prev];
              next[existingIdx] = { ...next[existingIdx], ...item, is_read: Boolean(item.is_read ?? next[existingIdx].is_read) };
              return next;
            }
            return prev.filter((e) => e.id !== item.id);
          }
          if (!isUpdate && matchesMailbox && matchesLabel && matchesFolder) {
            return [{ ...item, is_read: Boolean(item.is_read) }, ...prev];
          }
          return prev;
        });

        setSelected((prev) =>
          prev && prev.id === item.id
            ? { ...prev, label: item.label, confidence: item.confidence }
            : prev,
        );

        if (isUpdate) {
          if (matchesMailbox) {
            setLabelCounts((prev) => {
              const next = { ...prev };
              if (item.previous_label && item.previous_label !== item.label) {
                next[item.previous_label] = Math.max(0, (next[item.previous_label] ?? 1) - 1);
              }
              next[item.label] = (next[item.label] ?? 0) + 1;
              return next;
            });
          }
          return;
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
          setFolderCounts((prev) => ({
            ...prev,
            [itemFolder]: (prev[itemFolder] ?? 0) + 1,
          }));
        }
      } catch {
        /* ignore */
      }
    });
    source.addEventListener("sync.progress", (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data) as {
          mailbox_id?: number;
          message?: string;
          imported?: number;
          total?: number;
        };
        if (data.mailbox_id != null) {
          setIdInSet(setSyncingIds, data.mailbox_id, true);
          syncingIdsRef.current = new Set(syncingIdsRef.current).add(data.mailbox_id);
        }
        const imported = data.imported ?? 0;
        const total = data.total ?? 0;
        setActionStatus({
          type: "sync",
          message: withAccount(
            data.mailbox_id,
            data.message || `Syncing… ${imported}${total ? ` / ${total}` : ""}`,
          ),
        });
      } catch {
        /* ignore */
      }
    });
    source.addEventListener("reclassify.progress", (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data) as {
          mailbox_id?: number;
          message?: string;
          updated?: number;
          total?: number;
        };
        if (data.mailbox_id != null) {
          setIdInSet(setReclassifyingIds, data.mailbox_id, true);
          reclassifyingIdsRef.current = new Set(reclassifyingIdsRef.current).add(data.mailbox_id);
        }
        const updated = data.updated ?? 0;
        const total = data.total ?? 0;
        setActionStatus({
          type: "reclassify",
          message: withAccount(
            data.mailbox_id,
            data.message || `Reclassifying… ${updated}${total ? ` / ${total}` : ""}`,
          ),
        });
      } catch {
        /* ignore */
      }
    });
    source.addEventListener("reclassify.done", (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data) as {
          mailbox_id?: number;
          state?: string;
          message?: string;
          updated?: number;
          total?: number;
        };
        const mailboxId = data.mailbox_id;
        if (mailboxId != null) {
          const next = new Set(reclassifyingIdsRef.current);
          next.delete(mailboxId);
          reclassifyingIdsRef.current = next;
          setReclassifyingIds(next);
        }
        void load();
        const othersRemain =
          syncingIdsRef.current.size > 0 || reclassifyingIdsRef.current.size > 0;
        const msg = withAccount(
          mailboxId,
          data.message ||
            (data.state === "error"
              ? "Reclassify failed"
              : data.state === "stopped"
                ? "Reclassify stopped"
                : `Reclassify complete${data.updated != null ? ` — ${data.updated} updated` : ""}`),
        );
        if (data.state === "error") {
          setActionStatus({ type: "error", message: msg });
        } else if (othersRemain) {
          /* Keep remaining row spinner; don't claim the whole app finished. */
        } else if (data.state === "stopped") {
          setActionStatus({ type: "success", message: msg });
          window.setTimeout(() => setActionStatus(null), 4000);
        } else {
          setActionStatus({ type: "success", message: msg });
          window.setTimeout(() => setActionStatus(null), 4000);
        }
      } catch {
        void load();
      }
    });
    source.addEventListener("sync.done", (evt) => {
      try {
        const data = JSON.parse((evt as MessageEvent).data) as {
          mailbox_id?: number;
          state?: string;
          message?: string;
          imported?: number;
        };
        const mailboxId = data.mailbox_id;
        if (mailboxId != null) {
          const next = new Set(syncingIdsRef.current);
          next.delete(mailboxId);
          syncingIdsRef.current = next;
          setSyncingIds(next);
        }
        void load();
        const othersRemain =
          syncingIdsRef.current.size > 0 || reclassifyingIdsRef.current.size > 0;
        const msg = withAccount(
          mailboxId,
          data.message ||
            (data.state === "error"
              ? "Sync failed"
              : data.state === "stopped"
                ? "Sync stopped"
                : `Sync complete${data.imported != null ? ` — ${data.imported} new` : ""}`),
        );
        if (data.state === "error") {
          setActionStatus({ type: "error", message: msg });
        } else if (othersRemain) {
          /* Keep remaining row spinner; don't claim the whole app finished. */
        } else if (data.state === "stopped") {
          setActionStatus({ type: "success", message: msg });
          window.setTimeout(() => setActionStatus(null), 4000);
        } else {
          setActionStatus({ type: "success", message: msg });
          window.setTimeout(() => setActionStatus(null), 4000);
        }
      } catch {
        void load();
      }
    });
    source.onerror = () => setLive(false);
    return () => source.close();
  }, [load]);

  useEffect(() => {
    applyTheme(themePref);
    if (themePref !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [themePref]);

  useEffect(() => {
    applyFontFamily(fontFamily);
  }, [fontFamily]);

  useEffect(() => {
    applyFontSize(fontSize);
  }, [fontSize]);

  function persistPaneWidths() {
    try {
      localStorage.setItem(ACCOUNTS_W_KEY, String(Math.round(widthsRef.current.accounts)));
      localStorage.setItem(LIST_W_KEY, String(Math.round(widthsRef.current.list)));
    } catch {
      /* ignore */
    }
  }

  function onSplitterPointerDown(which: "accounts" | "list") {
    return (event: PointerEvent<HTMLButtonElement>) => {
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      setResizing(true);
      dragRef.current = {
        which,
        startX: event.clientX,
        startAccounts: widthsRef.current.accounts,
        startList: widthsRef.current.list,
      };
    };
  }

  function onSplitterPointerMove(event: PointerEvent<HTMLButtonElement>) {
    const drag = dragRef.current;
    const shell = shellRef.current;
    if (!drag || !shell) return;
    const width = shell.getBoundingClientRect().width;
    const dx = event.clientX - drag.startX;
    if (drag.which === "accounts") {
      const max = Math.max(ACCOUNTS_MIN, width - drag.startList - READER_MIN - 12);
      setAccountsW(Math.round(Math.min(max, Math.max(ACCOUNTS_MIN, drag.startAccounts + dx))));
    } else {
      const max = Math.max(LIST_MIN, width - drag.startAccounts - READER_MIN - 12);
      setListW(Math.round(Math.min(max, Math.max(LIST_MIN, drag.startList + dx))));
    }
  }

  function onSplitterPointerUp() {
    if (!dragRef.current) return;
    dragRef.current = null;
    setResizing(false);
    persistPaneWidths();
  }

  function chooseTheme(next: ThemePref) {
    setThemePref(next);
    saveThemePref(next);
  }

  function chooseViewMode(next: ViewMode) {
    setViewMode(next);
    saveViewMode(next);
  }

  function chooseFontFamily(next: FontFamily) {
    setFontFamily(next);
    saveFontFamily(next);
  }

  function chooseFontSize(next: FontSize) {
    setFontSize(next);
    saveFontSize(next);
  }

  function openSettings(section: SettingsSection = "appearance") {
    setSettingsSection(section);
    setSettingsOpen(true);
  }

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

  const listRows = useMemo((): ListRow[] => {
    const rows: ListRow[] = [];
    for (const group of dateGroups) {
      rows.push({
        kind: "group",
        key: group.key,
        heading: group.heading,
        count: group.items.length,
      });
      if (collapsedDates.has(group.key)) continue;
      for (const email of group.items) {
        rows.push({ kind: "email", email });
      }
    }
    return rows;
  }, [collapsedDates, dateGroups]);

  const listRowsRef = useRef(listRows);
  listRowsRef.current = listRows;
  const viewModeRef = useRef(viewMode);
  viewModeRef.current = viewMode;

  const listVirtualizer = useVirtualizer({
    count: loading ? 0 : listRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: (index) =>
      listRowsRef.current[index]?.kind === "group"
        ? LIST_ROW_GROUP_H
        : emailRowHeight(viewModeRef.current),
    overscan: LIST_OVERSCAN,
    getItemKey: (index) => {
      const row = listRowsRef.current[index];
      if (!row) return index;
      return row.kind === "group" ? `g-${row.key}` : `e-${row.email.id}`;
    },
  });

  const virtualItems = listVirtualizer.getVirtualItems();
  const lastVirtualIndex = virtualItems.length ? virtualItems[virtualItems.length - 1].index : -1;

  useEffect(() => {
    listVirtualizer.measure();
  }, [viewMode, listVirtualizer]);

  useEffect(() => {
    if (loading || lastVirtualIndex < 0) return;
    if (lastVirtualIndex >= listRows.length - LIST_OVERSCAN) void loadMore();
  }, [lastVirtualIndex, listRows.length, loadMore, loading]);

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
    const name = accountName(id) || "mailbox";
    setIdInSet(setSyncingIds, id, true);
    syncingIdsRef.current = new Set(syncingIdsRef.current).add(id);
    setActionStatus({ type: "sync", message: withAccount(id, "Syncing… listing Inbox") });
    try {
      const started = await syncMailbox(id);
      setActionStatus({
        type: "sync",
        message: withAccount(id, started.message || `Syncing ${name} in the background…`),
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Sync failed";
      setActionStatus({ type: "error", message: withAccount(id, msg) });
      setIdInSet(setSyncingIds, id, false);
      const next = new Set(syncingIdsRef.current);
      next.delete(id);
      syncingIdsRef.current = next;
    }
  }

  async function onStopSync(id: number) {
    try {
      const stopped = await stopSyncMailbox(id);
      setActionStatus({
        type: "sync",
        message: withAccount(id, stopped.message || "Stopping sync…"),
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to stop sync";
      setActionStatus({ type: "error", message: withAccount(id, msg) });
    }
  }

  async function onReclassify(id: number) {
    const name = accountName(id) || "mailbox";
    setIdInSet(setReclassifyingIds, id, true);
    reclassifyingIdsRef.current = new Set(reclassifyingIdsRef.current).add(id);
    setActionStatus({
      type: "reclassify",
      message: withAccount(id, "Reclassifying… running AI labels"),
    });
    try {
      const started = await reclassifyMailbox(id);
      setActionStatus({
        type: "reclassify",
        message: withAccount(id, started.message || `Reclassifying ${name} in the background…`),
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Reclassify failed";
      setActionStatus({ type: "error", message: withAccount(id, msg) });
      setIdInSet(setReclassifyingIds, id, false);
      const next = new Set(reclassifyingIdsRef.current);
      next.delete(id);
      reclassifyingIdsRef.current = next;
    }
  }

  async function onStopReclassify(id: number) {
    try {
      const stopped = await stopReclassifyMailbox(id);
      setActionStatus({
        type: "reclassify",
        message: withAccount(id, stopped.message || "Stopping reclassify…"),
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to stop reclassify";
      setActionStatus({ type: "error", message: withAccount(id, msg) });
    }
  }

  function onChangeCategory(nextLabel: EmailLabel) {
    if (!selected || savingLabel || pendingLabel || selected.label === nextLabel) return;
    setPendingLabel({ emailId: selected.id, nextLabel });
  }

  async function applyCategoryChange(useTraining: boolean) {
    if (!selected || !pendingLabel || savingLabel) return;
    const emailId = pendingLabel.emailId;
    const nextLabel = pendingLabel.nextLabel;
    const previous = selected.label;
    setPendingLabel(null);
    setSaveTraining(useTraining);
    setSavingLabel(true);
    setSelected((prev) => (prev && prev.id === emailId ? { ...prev, label: nextLabel } : prev));
    setEmails((prev) => {
      const currentLabel = filterRef.current.label;
      if (currentLabel !== "all" && currentLabel !== nextLabel) {
        return prev.filter((item) => item.id !== emailId);
      }
      return prev.map((item) => (item.id === emailId ? { ...item, label: nextLabel } : item));
    });
    try {
      const updated = await updateEmailLabel(emailId, nextLabel, useTraining);
      setSelected((prev) => (prev && prev.id === emailId ? { ...prev, ...updated } : prev));
      if (useTraining) {
        setUnusedTraining((count) => count + 1);
        void refreshPromptStatus();
      }
    } catch (err) {
      setSelected((prev) => (prev && prev.id === emailId ? { ...prev, label: previous } : prev));
      setEmails((prev) =>
        prev.map((item) => (item.id === emailId ? { ...item, label: previous } : item))
      );
      setBanner(err instanceof Error ? err.message : "Could not update category");
    } finally {
      setSavingLabel(false);
    }
  }

  async function onUpdatePrompt() {
    setUpdatingPrompt(true);
    setActionStatus({ type: "reclassify", message: "Updating classify prompt from training data…" });
    try {
      const result = await updateClassifyPrompt();
      await refreshPromptStatus();
      setActionStatus({
        type: "success",
        message: result.message || `Classify prompt updated from ${result.example_count} example(s)`,
      });
      window.setTimeout(() => setActionStatus(null), 4000);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to update classify prompt";
      setActionStatus({ type: "error", message: msg });
    } finally {
      setUpdatingPrompt(false);
    }
  }

  async function onOpenEmail(id: number) {
    setSelectedId(id);
    setSaveTraining(false);
    setPendingLabel(null);
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
        return prev.map((item) =>
          item.id === id
            ? { ...item, is_read: true, folder: detail.folder ?? item.folder }
            : item
        );
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

  function selectFolder(next: "all" | MailFolder) {
    scrollRef.current?.scrollTo(0, 0);
    if (folder === next) {
      setEmails([]);
      void loadFirstPage();
      return;
    }
    setFolder(next);
  }

  const selectedMailbox = selectedMailboxId != null ? mailboxById.get(selectedMailboxId) : null;
  const readerAccount =
    selected != null ? mailboxById.get(selected.mailbox_id)?.email_address ?? "" : "";

  return (
    <div
      ref={shellRef}
      className={resizing ? "app-shell is-resizing" : "app-shell"}
      style={
        {
          "--accounts-w": `${accountsW}px`,
          "--list-w": `${listW}px`,
        } as CSSProperties
      }
    >
      <aside className="pane-accounts">
        <div className="accounts-top">
          <div className="brand-mini">Auto AI Email Checker</div>
            <div className="accounts-top-actions">
            <div className="live-mini" data-live={live}>
              <span className="dot" />
              {live ? "Live" : "…"}
            </div>
            <button
              type="button"
              className="settings-btn"
              aria-label="Settings"
              aria-expanded={settingsOpen}
              onClick={() => openSettings("appearance")}
            >
              ⚙
            </button>
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

        <div className="prompt-train">
          <button
            type="button"
            className="action-btn"
            onClick={() => openSettings("training")}
          >
            {unusedTraining > 0 ? `Training (${unusedTraining})` : "Training"}
          </button>
          <p className="prompt-train-hint">
            {unusedTraining > 0
              ? `${unusedTraining} training example${unusedTraining === 1 ? "" : "s"} ready`
              : "Correct a category and save it as training data first"}
          </p>
        </div>

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
                    className={syncingIds.has(box.id) ? "action-btn busy" : "action-btn"}
                    disabled={reclassifyingIds.has(box.id)}
                    onClick={() => void (syncingIds.has(box.id) ? onStopSync(box.id) : onSync(box.id))}
                  >
                    {syncingIds.has(box.id) ? (
                      <>
                        <span className="spinner" aria-hidden="true" />
                        Stop sync
                      </>
                    ) : (
                      "Sync"
                    )}
                  </button>
                  <button
                    type="button"
                    className={reclassifyingIds.has(box.id) ? "action-btn busy" : "action-btn"}
                    disabled={syncingIds.has(box.id)}
                    onClick={() =>
                      void (reclassifyingIds.has(box.id) ? onStopReclassify(box.id) : onReclassify(box.id))
                    }
                  >
                    {reclassifyingIds.has(box.id) ? (
                      <>
                        <span className="spinner" aria-hidden="true" />
                        Stop reclassify
                      </>
                    ) : (
                      "Reclassify"
                    )}
                  </button>
                  <button
                    type="button"
                    className="action-btn danger"
                    disabled={syncingIds.has(box.id) || reclassifyingIds.has(box.id)}
                    onClick={() => void onDisconnect(box.id)}
                  >
                    Remove
                  </button>
                </div>
                {(syncingIds.has(box.id) || reclassifyingIds.has(box.id)) && (
                  <div className="account-progress" role="status">
                    <span className="spinner" aria-hidden="true" />
                    {syncingIds.has(box.id)
                      ? "Sync in progress — click Stop sync to cancel"
                      : "Reclassify in progress — click Stop reclassify to cancel"}
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

      <button
        type="button"
        className="pane-splitter"
        aria-label="Resize accounts pane"
        onPointerDown={onSplitterPointerDown("accounts")}
        onPointerMove={onSplitterPointerMove}
        onPointerUp={onSplitterPointerUp}
        onPointerCancel={onSplitterPointerUp}
      />

      <section className={`pane-list view-${viewMode}`}>
        <header className="list-header">
          <div className="list-title">
            <div className="view-toggle" role="radiogroup" aria-label="Inbox view">
              {VIEW_MODES.map((mode) => (
                <button
                  key={mode}
                  type="button"
                  role="radio"
                  aria-checked={viewMode === mode}
                  className={viewMode === mode ? "view-chip active" : "view-chip"}
                  onClick={() => chooseViewMode(mode)}
                >
                  {mode === "list" ? "List" : mode === "table" ? "Table" : "Card"}
                </button>
              ))}
            </div>
            <h2>
              {selectedMailbox ? selectedMailbox.email_address : "All accounts"}
            </h2>
          </div>
          <div className="folder-badges" role="tablist" aria-label="Mail folders">
            <button
              type="button"
              className={folder === "all" ? "folder-badge active" : "folder-badge"}
              onClick={() => selectFolder("all")}
            >
              all
              <span className="count-pill">{allCount}</span>
            </button>
            {MAIL_FOLDERS.map((item) => (
              <button
                key={item}
                type="button"
                className={
                  folder === item ? `folder-badge active folder-${item}` : `folder-badge folder-${item}`
                }
                onClick={() => selectFolder(item)}
              >
                {MAIL_FOLDER_TITLES[item]}
                <span className="count-pill">{folderCounts[item]}</span>
              </button>
            ))}
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
                {CLASSIFY_LABEL_TITLES[item]}
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

        <div className={`message-scroll view-${viewMode}`} ref={scrollRef}>
          {viewMode === "table" && !loading && listRows.length > 0 && (
            <div className="msg-table-head" aria-hidden="true">
              <span>From</span>
              <span>Subject</span>
              <span>Category</span>
              <span>Folder</span>
              <span>Date</span>
            </div>
          )}
          {!loading && listRows.length > 0 && (
            <div
              className="virtual-list"
              style={{ height: listVirtualizer.getTotalSize() }}
            >
              {virtualItems.map((virtualRow) => {
                const row = listRows[virtualRow.index];
                if (!row) return null;
                const style: CSSProperties = {
                  transform: `translateY(${virtualRow.start}px)`,
                };
                if (row.kind === "group") {
                  const collapsed = collapsedDates.has(row.key);
                  return (
                    <div
                      key={virtualRow.key}
                      data-index={virtualRow.index}
                      ref={listVirtualizer.measureElement}
                      className="virtual-row"
                      style={style}
                    >
                      <button
                        type="button"
                        className="msg-group-head"
                        onClick={() => toggleDateGroup(row.key)}
                        aria-expanded={!collapsed}
                      >
                        <span className="date-chevron" aria-hidden="true">
                          {collapsed ? "▸" : "▾"}
                        </span>
                        <span className="date-heading">{row.heading}</span>
                        <span className="group-count">{row.count}</span>
                      </button>
                    </div>
                  );
                }
                const email = row.email;
                const when = formatItemTimeAndDay(email.received_at);
                const accountAddress =
                  selectedMailboxId == null
                    ? mailboxById.get(email.mailbox_id)?.email_address ?? ""
                    : "";
                return (
                  <div
                    key={virtualRow.key}
                    data-index={virtualRow.index}
                    ref={listVirtualizer.measureElement}
                    className="virtual-row"
                    style={style}
                  >
                    <MessageRow
                      email={email}
                      viewMode={viewMode}
                      active={selectedId === email.id}
                      showLabel={label === "all"}
                      accountAddress={accountAddress}
                      when={when}
                      folder={mailFolderOf(email)}
                      folderTitle={MAIL_FOLDER_TITLES[mailFolderOf(email)]}
                      onOpen={(id) => void onOpenEmail(id)}
                    />
                  </div>
                );
              })}
            </div>
          )}
          {!loading && !emails.length && mailboxes.length > 0 && (
            <p className="hint pad">
              {folder === "all"
                ? "No classified emails yet. Sync an account."
                : `No emails in ${MAIL_FOLDER_TITLES[folder]}. Sync to refresh folder labels.`}
            </p>
          )}
          {!loading && !mailboxes.length && (
            <p className="hint pad">Add an account to start.</p>
          )}
          {loadingMore && <p className="hint pad loading-more">Loading more…</p>}
        </div>
      </section>

      <button
        type="button"
        className="pane-splitter"
        aria-label="Resize message list"
        onPointerDown={onSplitterPointerDown("list")}
        onPointerMove={onSplitterPointerMove}
        onPointerUp={onSplitterPointerUp}
        onPointerCancel={onSplitterPointerUp}
      />

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
                    {readerAccount ? (
                      <p>
                        Account <span className="to-address">{readerAccount}</span>
                      </p>
                    ) : null}
                    <p>
                      Folder{" "}
                      <span className={`folder-pill folder-${mailFolderOf(selected)}`}>
                        {MAIL_FOLDER_TITLES[mailFolderOf(selected)]}
                      </span>
                    </p>
                  </div>
                </div>
                <div className="reader-side">
                  <select
                    className={`label-select label-${selected.label}`}
                    value={selected.label}
                    disabled={savingLabel || pendingLabel != null}
                    aria-label="Email category"
                    onChange={(event) => onChangeCategory(event.target.value as EmailLabel)}
                  >
                    {CLASSIFY_LABELS.map((item) => (
                      <option key={item} value={item}>
                        {CLASSIFY_LABEL_TITLES[item]}
                      </option>
                    ))}
                  </select>
                  <label className="train-check">
                    <input
                      type="checkbox"
                      checked={saveTraining}
                      onChange={(event) => setSaveTraining(event.target.checked)}
                    />
                    Save as training data
                  </label>
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

      {pendingLabel && (
        <div className="dialog-backdrop" role="presentation">
          <div
            className="dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="train-confirm-title"
          >
            <header className="dialog-header">
              <h3 id="train-confirm-title">Prompt training</h3>
            </header>
            <div className="dialog-body">
              <p className="dialog-hint">Use this email as prompt update training data?</p>
              <div className="dialog-actions">
                <button
                  type="button"
                  className="action-btn"
                  onClick={() => void applyCategoryChange(false)}
                >
                  No
                </button>
                <button
                  type="button"
                  className="primary-btn"
                  onClick={() => void applyCategoryChange(true)}
                >
                  Yes
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

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
      {settingsOpen && (
        <SettingsPage
          section={settingsSection}
          onSectionChange={setSettingsSection}
          onClose={() => setSettingsOpen(false)}
          themePref={themePref}
          onThemeChange={chooseTheme}
          viewMode={viewMode}
          onViewModeChange={chooseViewMode}
          fontFamily={fontFamily}
          onFontFamilyChange={chooseFontFamily}
          fontSize={fontSize}
          onFontSizeChange={chooseFontSize}
          mailboxes={mailboxes}
          unusedTraining={unusedTraining}
          updatingPrompt={updatingPrompt}
          onUpdatePrompt={onUpdatePrompt}
          initialMailboxId={selectedMailboxId}
        />
      )}
    </div>
  );
}
