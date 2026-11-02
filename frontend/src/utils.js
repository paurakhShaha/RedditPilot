import { useEffect, useState } from "react";

export const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export const STATUS_TONE = {
  "Pending Review": "amber",
  Approved: "sage",
  Rejected: "red",
  Scheduled: "blue",
  Published: "sage",
  Failed: "red",
  Archived: "neutral",
  planned: "neutral",
  generating: "amber",
  draft_ready: "blue",
  approved: "sage",
  published: "sage",
  skipped: "neutral",
  failed: "red",
  uncertain: "amber",
  suitable: "sage",
  review: "amber",
  prohibited: "red",
  not_recommended: "red",
  connected: "sage",
  unverified: "amber",
  disconnected: "neutral",
};

export const STATUS_LABEL = {
  planned: "Planned",
  generating: "Generating",
  draft_ready: "Draft ready",
  approved: "Approved",
  published: "Published",
  skipped: "Skipped",
  failed: "Failed",
  suitable: "Suitable",
  review: "Needs review",
  prohibited: "Prohibited",
  not_recommended: "Not recommended",
};

export function formatDate(value, opts = {}) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    ...opts,
  }).format(date);
}

export function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(date);
}

export function timeAgo(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 45) return seconds >= 0 ? "just now" : "in a moment";
  const units = [
    ["year", 31536000],
    ["month", 2592000],
    ["week", 604800],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, size] of units) {
    if (abs >= size) {
      const amount = Math.round(abs / size);
      const label = `${amount} ${unit}${amount === 1 ? "" : "s"}`;
      return seconds >= 0 ? `${label} ago` : `in ${label}`;
    }
  }
  return "just now";
}

export function formatNumber(value) {
  return new Intl.NumberFormat().format(Number(value || 0));
}

export function compactNumber(value) {
  const number = Number(value || 0);
  if (Math.abs(number) >= 1_000_000) return `${(number / 1_000_000).toFixed(1).replace(/\.0$/, "")}m`;
  if (Math.abs(number) >= 1000) return `${(number / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return formatNumber(number);
}

export function statusLabel(status) {
  return STATUS_LABEL[status] || status || "—";
}

export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

export function localDateKey(value) {
  const date = value instanceof Date ? value : new Date(value);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function startOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

export function addMonths(date, delta) {
  return new Date(date.getFullYear(), date.getMonth() + delta, 1);
}

export function monthCells(monthDate) {
  const first = startOfMonth(monthDate);
  const mondayOffset = (first.getDay() + 6) % 7;
  const start = new Date(first);
  start.setDate(first.getDate() - mondayOffset);
  return Array.from({ length: 42 }, (_, index) => {
    const day = new Date(start);
    day.setDate(start.getDate() + index);
    return day;
  });
}

export function daysSince(value) {
  if (!value) return null;
  const then = new Date(value);
  if (Number.isNaN(then.getTime())) return null;
  return Math.max(0, Math.floor((Date.now() - then.getTime()) / 86400000));
}

export function truncate(text, length = 120) {
  if (!text) return "";
  return text.length > length ? `${text.slice(0, length).trimEnd()}…` : text;
}

export function pluralize(count, singular, plural) {
  return `${count} ${count === 1 ? singular : plural || `${singular}s`}`;
}

export function safeHost(url) {
  if (!url) return "";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function useLocalStorage(key, initial) {
  const [value, setValue] = useState(() => {
    try {
      const stored = localStorage.getItem(key);
      return stored !== null ? JSON.parse(stored) : initial;
    } catch {
      return initial;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* storage can be unavailable */
    }
  }, [key, value]);
  return [value, setValue];
}
