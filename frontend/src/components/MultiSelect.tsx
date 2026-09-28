import { useEffect, useRef, useState } from "react";

/** Dropdown button that opens a checkbox list for picking multiple values. */
export default function MultiSelect({
  label,
  options,
  values,
  onChange,
}: {
  label: string;
  options: string[];
  values: string[];
  onChange: (next: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // Close on outside click / Escape so the popover behaves like a native select.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const toggle = (v: string) =>
    onChange(values.includes(v) ? values.filter((x) => x !== v) : [...values, v]);

  const summary =
    values.length === 0
      ? label
      : values.length === 1
        ? values[0]
        : `${values.length} selected`;

  return (
    <div className="multi-select" ref={rootRef}>
      <button
        type="button"
        className={`multi-select-btn ${values.length > 0 ? "active" : ""}`}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        {summary} <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="multi-select-pop" role="listbox">
          {values.length > 0 && (
            <button
              type="button"
              className="link multi-select-clear"
              onClick={() => onChange([])}
            >
              Clear
            </button>
          )}
          {options.map((o) => (
            <label key={o} className="multi-select-opt">
              <input
                type="checkbox"
                checked={values.includes(o)}
                onChange={() => toggle(o)}
              />
              <span className="multi-select-opt-label">{o}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
