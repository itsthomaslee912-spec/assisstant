import type { EmailItem, EmailLabel, MailFolder } from "../api";
import { CLASSIFY_LABEL_TITLES } from "../labels";
import type { ViewMode } from "../prefs";

export default function MessageRow({
  email,
  viewMode,
  active,
  showLabel,
  accountAddress,
  when,
  folderTitle,
  folder,
  onOpen,
}: {
  email: EmailItem;
  viewMode: ViewMode;
  active: boolean;
  showLabel: boolean;
  accountAddress: string;
  when: { time: string; day: string };
  folderTitle: string;
  folder: MailFolder;
  onOpen: (id: number) => void;
}) {
  const itemClass = [
    viewMode === "table" ? "msg-row" : viewMode === "card" ? "msg-card" : "msg-item",
    active ? "active" : "",
    email.is_read ? "" : "unread",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button type="button" className={itemClass} onClick={() => onOpen(email.id)}>
      {viewMode === "table" ? (
        <>
          <span className="msg-col from">
            <strong>{senderName(email.sender)}</strong>
            {accountAddress ? <span className="msg-account">{accountAddress}</span> : null}
          </span>
          <span className="msg-col subject">{email.subject || "(no subject)"}</span>
          <span className={`msg-col label list-label label-${email.label}`}>
            {CLASSIFY_LABEL_TITLES[email.label as EmailLabel] ?? email.label}
          </span>
          <span className={`msg-col folder-pill folder-${folder}`}>{folderTitle}</span>
          <span className="msg-col date">
            <span className="msg-time">{when.time}</span>
            {when.day && <span className="msg-day">{when.day}</span>}
          </span>
        </>
      ) : (
        <>
          <span className={`avatar soft label-${email.label}`}>
            {initialsFrom(senderName(email.sender))}
          </span>
          <span className="msg-body">
            <span className="msg-top">
              <span className="msg-from">
                <strong>{senderName(email.sender)}</strong>
                {accountAddress ? <span className="msg-account">{accountAddress}</span> : null}
              </span>
              <span className="msg-meta">
                {(showLabel || viewMode === "card") && (
                  <span className={`label list-label label-${email.label}`}>
                    {CLASSIFY_LABEL_TITLES[email.label as EmailLabel] ?? email.label}
                  </span>
                )}
                {viewMode !== "card" && (
                  <span className={`folder-pill folder-${folder}`}>{folderTitle}</span>
                )}
                {viewMode !== "card" && (
                  <span className={email.is_read ? "read-pill" : "new-pill"}>
                    {email.is_read ? "Read" : "NEW"}
                  </span>
                )}
                <time>
                  <span className="msg-time">{when.time}</span>
                  {when.day && <span className="msg-day">{when.day}</span>}
                </time>
              </span>
            </span>
            <span className="msg-subject">{email.subject || "(no subject)"}</span>
            <span className="msg-snippet">{email.snippet}</span>
            {viewMode === "card" && (
              <span className="msg-card-meta">
                <span className={`folder-pill folder-${folder}`}>{folderTitle}</span>
                <span className={email.is_read ? "read-pill" : "new-pill"}>
                  {email.is_read ? "Read" : "NEW"}
                </span>
              </span>
            )}
          </span>
        </>
      )}
    </button>
  );
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
