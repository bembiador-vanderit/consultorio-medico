import { forwardRef, useId, useState, type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from "react";

export const cx = (...values: (string | false | undefined)[]) => values.filter(Boolean).join(" ");
export type Tone = "neutral" | "success" | "warning" | "danger" | "info";
export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "outline" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  loadingLabel?: string;
  icon?: ReactNode;
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading = false, loadingLabel = "Procesando…", icon, disabled, children, className, type = "button", ...props }, ref,
) {
  return <button {...props} ref={ref} type={type} disabled={disabled || loading} aria-busy={loading || undefined}
    className={cx("atlas-button", `atlas-button--${variant}`, `atlas-button--${size}`, className)}>
    {loading ? <Spinner /> : icon && <span aria-hidden="true" className="atlas-icon">{icon}</span>}
    {loading ? loadingLabel : children}
  </button>;
});

export function IconButton({ label, children, loading, ...props }: Omit<ButtonProps, "aria-label" | "loadingLabel"> & { label: string }) {
  return <Button {...props} loading={false} disabled={props.disabled || loading} aria-busy={loading || undefined} aria-label={label} className={cx("atlas-icon-button", props.className)}>
    <span aria-hidden="true">{loading ? <Spinner /> : children}</span>
  </Button>;
}

export function Card({ compact, className, ...props }: HTMLAttributes<HTMLDivElement> & { compact?: boolean }) {
  return <div {...props} className={cx("atlas-card", compact && "atlas-card--compact", className)} />;
}

/** A single action card is a real button. Never nest controls inside it. */
export function ActionCard({ className, type = "button", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button {...props} type={type} className={cx("atlas-card", "atlas-action-card", className)} />;
}

export function StatusBadge({ tone = "neutral", className, ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return <span {...props} className={cx("atlas-badge", `atlas-tone--${tone}`, className)} />;
}

export function Alert({ tone = "info", title, children, className, ...props }: Omit<HTMLAttributes<HTMLDivElement>, "title"> & { tone?: Tone; title: string }) {
  return <div role={tone === "danger" ? "alert" : "status"} {...props} className={cx("atlas-alert", `atlas-tone--${tone}`, className)}>
    <strong>{title}</strong>{children && <div>{children}</div>}
  </div>;
}

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="atlas-empty"><h3 className="atlas-card-title">{title}</h3>{description && <p className="atlas-muted">{description}</p>}{action}</div>;
}

export function Spinner() { return <span aria-hidden="true" className="atlas-spinner" />; }
export function LoadingState({ label = "Cargando…" }: { label?: string }) {
  return <div role="status" className="atlas-loading"><Spinner /><span>{label}</span></div>;
}
export function Skeleton({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} aria-hidden="true" className={cx("atlas-skeleton", className)} />;
}
export function Divider() { return <hr className="atlas-divider" />; }

type HeaderProps = { title: string; description?: string; actions?: ReactNode; eyebrow?: string };
export function PageHeader({ title, description, actions, eyebrow }: HeaderProps) {
  return <header className="atlas-page-header"><div>{eyebrow && <p className="atlas-caption">{eyebrow}</p>}<h1 className="atlas-page-title">{title}</h1>{description && <p className="atlas-muted">{description}</p>}</div>{actions && <div className="atlas-actions">{actions}</div>}</header>;
}
export function SectionHeader({ title, description, actions }: HeaderProps) {
  return <header className="atlas-page-header"><div><h2 className="atlas-section-title">{title}</h2>{description && <p className="atlas-muted">{description}</p>}</div>{actions}</header>;
}
export function PageContainer({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={cx("atlas-page", className)} />;
}
export function Stack({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={cx("atlas-stack", className)} />;
}
export function CardGrid({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div {...props} className={cx("atlas-grid", className)} />;
}

/** Focusable description for short, supplemental help; essential instructions stay visible. */
export function Tooltip({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  return <span className="atlas-tooltip" data-open={(hovered || focused) && !dismissed}
    onMouseEnter={() => { setHovered(true); setDismissed(false); }} onMouseLeave={() => setHovered(false)}
    onKeyDown={(event) => { if (event.key === "Escape") { event.stopPropagation(); setDismissed(true); } }}>
    <button type="button" className="atlas-tooltip-trigger" aria-describedby={id}
      onFocus={() => { setFocused(true); setDismissed(false); }} onBlur={() => setFocused(false)}>{children}</button>
    <span id={id} role="tooltip" className="atlas-tooltip-content">{label}</span>
  </span>;
}
