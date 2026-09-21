import type { EmailLabel } from "./api";

export const CLASSIFY_LABELS: EmailLabel[] = [
  "job_alert",
  "applied",
  "screening",
  "interview",
  "assessment",
  "offer",
  "rejected",
  "others",
];

export const CLASSIFY_LABEL_TITLES: Record<EmailLabel, string> = {
  job_alert: "Job alert",
  applied: "Applied",
  screening: "Screening",
  interview: "Interview",
  assessment: "Assessment",
  offer: "Offer",
  rejected: "Rejected",
  others: "Others",
};

export const EMPTY_LABEL_COUNTS: Record<EmailLabel, number> = {
  job_alert: 0,
  applied: 0,
  screening: 0,
  interview: 0,
  assessment: 0,
  offer: 0,
  rejected: 0,
  others: 0,
};

export const LABEL_BAR_COLORS: Record<EmailLabel, string> = {
  job_alert: "#ff9f43",
  applied: "#b7a6ff",
  screening: "#8ee0b5",
  interview: "#7ec8ff",
  assessment: "#f0b429",
  offer: "#5ecfc0",
  rejected: "#e36a6a",
  others: "#8b95a7",
};
