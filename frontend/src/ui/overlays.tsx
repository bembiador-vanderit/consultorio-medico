import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Button, IconButton, cx } from "./primitives";

type DialogProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  closeLabel?: string;
};

// A shared lock also supports a modal opened from a drawer without early unlock.
let scrollLocks = 0;
let previousOverflow = "";
function lockScroll() {
  if (scrollLocks++ === 0) {
    previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  }
  return () => { if (--scrollLocks === 0) document.body.style.overflow = previousOverflow; };
}

function Dialog({ open, onClose, title, description, children, footer, closeLabel = "Cerrar panel", drawer = false }: DialogProps & { drawer?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!open || !dialog) return;
    const trigger = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.showModal(); // Browser top layer supplies inert background and focus containment.
    const unlock = lockScroll();
    titleRef.current?.focus();
    return () => {
      dialog.close();
      unlock();
      if (trigger?.isConnected) trigger.focus();
    };
  }, [open]);
  return createPortal(<dialog ref={ref} className={cx("atlas-dialog", drawer && "atlas-dialog--drawer")}
    aria-labelledby={titleId} aria-describedby={description ? descriptionId : undefined}
    onKeyDown={(event) => {
      if (event.key !== "Tab") return;
      const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(
        'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex]:not([tabindex="-1"])',
      )).filter((element) => element.tabIndex >= 0 && element.getClientRects().length > 0);
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (!first) { event.preventDefault(); titleRef.current?.focus(); }
      else if (event.shiftKey && (document.activeElement === first || document.activeElement === titleRef.current)) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    }}
    onCancel={(event) => { event.preventDefault(); onClose(); }}>
    <header className="atlas-dialog-header"><div><h2 id={titleId} ref={titleRef} tabIndex={-1} className="atlas-section-title">{title}</h2>
      {description && <p id={descriptionId} className="atlas-muted">{description}</p>}</div>
      <IconButton label={closeLabel} variant="ghost" onClick={onClose}>×</IconButton>
    </header>
    <div className="atlas-dialog-body">{children}</div>
    {footer && <footer className="atlas-dialog-footer">{footer}</footer>}
  </dialog>, document.body);
}

export function Modal(props: DialogProps) { return <Dialog {...props} />; }
export function Drawer(props: DialogProps) { return <Dialog {...props} drawer />; }

export type MenuAction = { id: string; label: string; onSelect: () => void; disabled?: boolean };
/** Disclosure of ordinary action buttons, intentionally not an ARIA application menu. */
export function Dropdown({ label, actions }: { label: string; actions: readonly MenuAction[] }) {
  const ref = useRef<HTMLDetailsElement>(null);
  const triggerRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && ref.current && !ref.current.contains(event.target)) ref.current.open = false;
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, []);
  function close() { if (ref.current) ref.current.open = false; triggerRef.current?.focus(); }
  return <details ref={ref} className="atlas-dropdown" onKeyDown={(event) => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); }
  }} onBlur={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null) && ref.current) ref.current.open = false;
  }}>
    <summary ref={triggerRef} className="atlas-button atlas-button--outline">{label}</summary>
    <div className="atlas-dropdown-content">{actions.map((action) => <Button key={action.id} variant="ghost" disabled={action.disabled}
      onClick={() => { close(); action.onSelect(); }}>{action.label}</Button>)}</div>
  </details>;
}
