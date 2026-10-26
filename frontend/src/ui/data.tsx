import { useId, useRef, type ReactNode } from "react";
import { EmptyState, LoadingState } from "./primitives";

type TabItem = { id: string; label: string; content: ReactNode; disabled?: boolean };
export function Tabs({ label, items, value, onChange }: { label: string; items: readonly TabItem[]; value: string; onChange: (id: string) => void }) {
  const id = useId();
  const refs = useRef(new Map<string, HTMLButtonElement>());
  const enabled = items.filter((item) => !item.disabled);
  return <div className="atlas-tabs"><div role="tablist" aria-label={label} className="atlas-tab-list">
    {items.map((item) => <button key={item.id} type="button" role="tab" id={`${id}-tab-${item.id}`} aria-controls={`${id}-panel-${item.id}`}
      aria-selected={value === item.id} tabIndex={value === item.id ? 0 : -1} disabled={item.disabled}
      ref={(element) => { if (element) refs.current.set(item.id, element); else refs.current.delete(item.id); }}
      onClick={() => onChange(item.id)} onKeyDown={(event) => {
        const index = enabled.findIndex((entry) => entry.id === item.id);
        const next = event.key === "ArrowRight" ? (index + 1) % enabled.length : event.key === "ArrowLeft" ? (index - 1 + enabled.length) % enabled.length : event.key === "Home" ? 0 : event.key === "End" ? enabled.length - 1 : -1;
        if (next >= 0) { event.preventDefault(); onChange(enabled[next].id); refs.current.get(enabled[next].id)?.focus(); }
      }}>{item.label}</button>)}
  </div>{items.map((item) => <div key={item.id} role="tabpanel" id={`${id}-panel-${item.id}`} aria-labelledby={`${id}-tab-${item.id}`}
    hidden={value !== item.id} tabIndex={0} className="atlas-tab-panel">{item.content}</div>)}</div>;
}

export type TableColumn<Row> = { id: string; header: ReactNode; render: (row: Row) => ReactNode; action?: boolean; sortDirection?: "ascending" | "descending" | "none" };
export function Table<Row>({ caption, columns, rows, rowKey, loading = false, loadingLabel = "Cargando registros…", emptyTitle = "No hay registros", emptyDescription }: {
  caption: string; columns: readonly TableColumn<Row>[]; rows: readonly Row[]; rowKey: (row: Row) => string | number;
  loading?: boolean; loadingLabel?: string; emptyTitle?: string; emptyDescription?: string;
}) {
  return <div className="atlas-table-scroll" role="region" aria-label={caption} tabIndex={0}>
    <table className="atlas-table" aria-busy={loading || undefined}><caption>{caption}</caption><thead><tr>{columns.map((column) =>
      <th key={column.id} scope="col" aria-sort={column.sortDirection} className={column.action ? "atlas-table-action" : undefined}>{column.header}</th>)}</tr></thead>
      <tbody>{loading ? <tr><td colSpan={columns.length}><LoadingState label={loadingLabel} /></td></tr> : rows.length === 0 ?
        <tr><td colSpan={columns.length}><EmptyState title={emptyTitle} description={emptyDescription} /></td></tr> : rows.map((row) =>
          <tr key={rowKey(row)}>{columns.map((column) => <td key={column.id} className={column.action ? "atlas-table-action" : undefined}>{column.render(row)}</td>)}</tr>)}</tbody>
    </table>
  </div>;
}
