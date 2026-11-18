import { useEffect, useRef, type ReactNode } from "react";
import { ArrowUpRight, Check, Copy, X, Info, ScanLine } from "lucide-react";
import type { Severity } from "../types";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="brand">
      <span className="brand-mark">
        <ScanLine size={23} strokeWidth={2.3} />
      </span>
      {!compact && (
        <>
          <span>
            Crawlens<span className="brand-dot">.</span>
          </span>
          <span className="brand-ai">AI</span>
        </>
      )}
    </div>
  );
}
export function Badge({ severity }: { severity: Severity }) {
  return (
    <span className={`badge ${severity}`}>
      <i />
      {severity === "critical" ? "Critical" : severity === "high"
        ? "High priority"
        : severity === "medium"
          ? "Medium"
          : "Low"}
    </span>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Check size={23} />
      </span>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function ExternalLink({
  url,
  children,
}: {
  url: string;
  children?: ReactNode;
}) {
  return (
    <a
      href={/^https?:\/\//.test(url) ? url : undefined}
      target="_blank"
      rel="noopener noreferrer"
      className="external-link"
    >
      {children ?? url}
      <ArrowUpRight size={13} />
    </a>
  );
}
export function Modal({
  title,
  children,
  close,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
  wide?: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = dialog.current;
    el?.showModal();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      el?.close();
      document.body.style.overflow = previous;
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className={`modal ${wide ? "wide" : ""}`}
      aria-labelledby="modal-title"
      onCancel={close}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="modal-inner">
        <div className="modal-heading">
          <h2 id="modal-title">{title}</h2>
          <button
            className="icon-button"
            onClick={close}
            aria-label="Close dialog"
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="notice">
      <Info size={16} />
      <div>{children}</div>
    </div>
  );
}
export function CopyButton({
  text,
  onCopy,
}: {
  text: string;
  onCopy: (message: string) => void;
}) {
  return (
    <button
      className="text-button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          onCopy("Copied to clipboard");
        } catch {
          onCopy(
            "Clipboard is unavailable. Select and copy the text manually.",
          );
        }
      }}
    >
      <Copy size={14} />
      Copy
    </button>
  );
}
