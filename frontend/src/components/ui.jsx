import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Icon, { Spinner } from "./Icons.jsx";

/* ------------------------------------------------------------------ buttons */
export function Button({
  children,
  variant = "default",
  size,
  icon,
  iconRight,
  loading = false,
  block = false,
  className = "",
  type = "button",
  ...rest
}) {
  const classes = [
    "btn",
    variant === "primary" && "btn-primary",
    variant === "ghost" && "btn-ghost",
    variant === "outline" && "btn-outline",
    variant === "danger" && "btn-danger",
    variant === "sage" && "btn-sage",
    size === "sm" && "btn-sm",
    size === "lg" && "btn-lg",
    block && "btn-block",
    className,
  ].filter(Boolean).join(" ");
  return (
    <button type={type} className={classes} disabled={loading || rest.disabled} {...rest}>
      {loading ? <Spinner size={14} /> : icon ? <Icon name={icon} size={size === "sm" ? 13 : 15} /> : null}
      {children}
      {iconRight ? <Icon name={iconRight} size={size === "sm" ? 13 : 15} /> : null}
    </button>
  );
}

export function IconButton({ icon, label, size, variant = "ghost", loading, className = "", ...rest }) {
  return (
    <button
      type="button"
      className={`btn btn-icon ${variant === "danger" ? "btn-danger" : variant === "ghost" ? "btn-ghost" : ""} ${size === "sm" ? "btn-sm" : ""} ${className}`}
      aria-label={label}
      title={label}
      disabled={loading || rest.disabled}
      {...rest}
    >
      {loading ? <Spinner size={14} /> : <Icon name={icon} size={size === "sm" ? 14 : 16} />}
    </button>
  );
}

/* ------------------------------------------------------------------ badges */
export function Badge({ children, tone = "neutral", dot = false, className = "" }) {
  return (
    <span className={`badge badge-${tone} ${className}`}>
      {dot && <span className={`dot ${tone === "sage" ? "green" : tone === "ember" ? "ember" : tone === "red" ? "red" : ""}`} />}
      {children}
    </span>
  );
}

const TONE_MAP = {
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

const LABELS = {
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
  unverified: "Unverified",
  disconnected: "Disconnected",
};

export function StatusBadge({ status, dot = true }) {
  const tone = TONE_MAP[status] || "neutral";
  const label = LABELS[status] || status || "—";
  return <Badge tone={tone} dot={dot}>{label}</Badge>;
}

/* ------------------------------------------------------------------ fields */
export function Field({ label, hint, error, optional, children, className = "", htmlFor }) {
  return (
    <div className={`field ${className}`}>
      {label && (
        <label htmlFor={htmlFor}>
          <span>{label}</span>
          {optional && <span className="optional">Optional</span>}
        </label>
      )}
      {children}
      {error ? <span className="field-error">{error}</span> : hint ? <span className="field-hint">{hint}</span> : null}
    </div>
  );
}

export function Switch({ checked, onChange, disabled, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className={`switch ${checked ? "on" : ""}`}
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
    />
  );
}

export function ToggleRow({ title, description, checked, onChange, disabled }) {
  return (
    <div className="switch-row">
      <div className="switch-copy">
        <strong>{title}</strong>
        {description && <span>{description}</span>}
      </div>
      <Switch checked={checked} onChange={onChange} disabled={disabled} label={title} />
    </div>
  );
}

export function CheckRow({ checked, onChange, children, disabled }) {
  return (
    <label className="check-row">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} disabled={disabled} />
      <span>{children}</span>
    </label>
  );
}

/* ------------------------------------------------------------------ page head */
export function PageHead({ eyebrow, title, description, actions }) {
  return (
    <div className="page-head">
      <div className="page-head-main">
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1 className="page-title">{title}</h1>
        {description && <p className="page-desc">{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

export function SectionHead({ title, subtitle, actions }) {
  return (
    <div className="row-between" style={{ marginBottom: 12 }}>
      <div>
        <h2 className="section-title" style={{ fontSize: 18 }}>{title}</h2>
        {subtitle && <p className="field-hint">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

/* ------------------------------------------------------------------ empty/loading */
export function EmptyState({ icon = "file", title, text, actions }) {
  return (
    <div className="empty">
      <div className="empty-mark"><Icon name={icon} size={21} /></div>
      <h3 className="empty-title">{title}</h3>
      {text && <p className="empty-text">{text}</p>}
      {actions && <div className="empty-actions">{actions}</div>}
    </div>
  );
}

export function LoadingBlock({ lines = 3, height = 14 }) {
  return (
    <div className="stack-sm" style={{ padding: 4 }}>
      {Array.from({ length: lines }).map((_, index) => (
        <div
          key={index}
          className="skeleton"
          style={{ height, width: index === lines - 1 ? "62%" : `${88 - index * 6}%` }}
        />
      ))}
    </div>
  );
}

export function ErrorBlock({ message, onRetry }) {
  return (
    <div className="empty">
      <div className="empty-mark" style={{ color: "var(--red)" }}><Icon name="alertCircle" size={21} /></div>
      <h3 className="empty-title">Could not load this view</h3>
      <p className="empty-text">{message}</p>
      {onRetry && <div className="empty-actions"><Button variant="outline" size="sm" icon="refresh" onClick={onRetry}>Try again</Button></div>}
    </div>
  );
}

/* ------------------------------------------------------------------ modal */
export function Modal({ open, onClose, title, subtitle, children, footer, size = "md", busy = false, closeOnBackdrop = true }) {
  const backdropRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key === "Escape" && !busy) onClose?.();
    };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open, busy, onClose]);

  if (!open) return null;

  return createPortal(
    <div
      className="overlay"
      ref={backdropRef}
      onMouseDown={(event) => {
        if (closeOnBackdrop && !busy && event.target === backdropRef.current) onClose?.();
      }}
    >
      <div
        className={`modal ${size === "lg" ? "modal-lg" : size === "sm" ? "modal-sm" : size === "md" ? "modal-md" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === "string" ? title : "Dialog"}
      >
        {(title || subtitle) && (
          <div className="modal-head">
            <div style={{ minWidth: 0 }}>
              {title && <h2 className="modal-title">{title}</h2>}
              {subtitle && <div className="modal-sub">{subtitle}</div>}
            </div>
            <IconButton className="modal-close" icon="close" label="Close" onClick={onClose} disabled={busy} />
          </div>
        )}
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>,
    document.body
  );
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title = "Are you sure?",
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  tone = "danger",
  busy = false,
  icon,
  children,
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      size="sm"
      busy={busy}
      footer={(
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>{cancelLabel}</Button>
          <Button variant={tone} onClick={onConfirm} loading={busy}>{confirmLabel}</Button>
        </>
      )}
    >
      <div className="row" style={{ alignItems: "flex-start", gap: 12 }}>
        {icon && <div className="empty-mark" style={{ width: 36, height: 36, marginBottom: 0 }}><Icon name={icon} size={18} /></div>}
        <div>
          {message && <p className="text-soft" style={{ fontSize: 13, lineHeight: 1.65 }}>{message}</p>}
          {children}
        </div>
      </div>
    </Modal>
  );
}

/* ------------------------------------------------------------------ toasts */
const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timers = useRef(new Map());

  const dismiss = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
    const timer = timers.current.get(id);
    if (timer) clearTimeout(timer);
    timers.current.delete(id);
  }, []);

  const push = useCallback((type, title, message) => {
    const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    setToasts((current) => [...current.slice(-3), { id, type, title, message }]);
    const timer = setTimeout(() => dismiss(id), type === "error" ? 8000 : 5200);
    timers.current.set(id, timer);
  }, [dismiss]);

  const api = useMemo(() => ({
    success: (title, message) => push("success", title, message),
    error: (title, message) => push("error", title, message),
    info: (title, message) => push("info", title, message),
    warning: (title, message) => push("warning", title, message),
    dismiss,
  }), [push, dismiss]);

  useEffect(() => () => {
    timers.current.forEach((timer) => clearTimeout(timer));
  }, []);

  return (
    <ToastContext.Provider value={api}>
      {children}
      {createPortal(
        <div className="toast-stack" aria-live="polite" aria-atomic="false">
          {toasts.map((toast) => (
            <div key={toast.id} className={`toast ${toast.type}`} role="status">
              <Icon
                name={toast.type === "success" ? "checkCircle" : toast.type === "error" ? "alertCircle" : toast.type === "warning" ? "alert" : "info"}
                size={17}
                style={{ marginTop: 1, flex: "none" }}
              />
              <div style={{ minWidth: 0 }}>
                <strong>{toast.title}</strong>
                {toast.message && <span>{toast.message}</span>}
              </div>
              <button type="button" className="toast-close" onClick={() => dismiss(toast.id)} aria-label="Dismiss">
                <Icon name="close" size={14} />
              </button>
            </div>
          ))}
        </div>,
        document.body
      )}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside ToastProvider");
  return context;
}

/* ------------------------------------------------------------------ misc */
export function CopyButton({ value, label = "Copy", size = "sm", variant = "outline", onCopied }) {
  const [copied, setCopied] = useState(false);
  const toast = useToast();

  const copy = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        const area = document.createElement("textarea");
        area.value = value;
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        document.execCommand("copy");
        area.remove();
      }
      setCopied(true);
      onCopied?.();
      setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error("Could not copy", "Your browser blocked clipboard access. Select the text and copy manually.");
    }
  };

  return (
    <Button size={size} variant={variant} icon={copied ? "check" : "copy"} onClick={copy}>
      {copied ? "Copied" : label}
    </Button>
  );
}

export function ScoreDots({ value, max = 5, label = true }) {
  return (
    <span className="row" style={{ gap: 7 }}>
      <span className="promo-dots" aria-label={`Promotional intensity ${value} of ${max}`}>
        {Array.from({ length: max }).map((_, index) => (
          <i key={index} className={index < value ? "on" : ""} />
        ))}
      </span>
      {label && <span className="muted" style={{ fontSize: 10.5 }}>{value}/{max}</span>}
    </span>
  );
}

export function Meter({ value, max = 5, tone }) {
  const percent = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className="meter">
      <div className="meter-fill" style={{ width: `${percent}%`, background: tone || undefined }} />
    </div>
  );
}

export function Callout({ tone = "info", title, children, icon }) {
  return (
    <div className={`callout ${tone}`}>
      <Icon name={icon || (tone === "danger" ? "alertCircle" : tone === "warning" ? "alert" : tone === "success" ? "checkCircle" : "info")} size={16} />
      <div>
        {title && <span className="callout-title">{title}</span>}
        {children}
      </div>
    </div>
  );
}

export function InlineEmpty({ children }) {
  return <p className="field-hint" style={{ padding: "8px 0" }}>{children}</p>;
}
