import { useId, useMemo, useState } from "react";

/** Autocomplete over asset names. Free text is allowed on purpose, so an unknown name can be tried
 *  and the API's honest "unknown asset" answer can be seen. */
export function AssetPicker({ label, value, onChange, names, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; names: string[]; placeholder?: string;
}) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const matches = useMemo(() => {
    const q = value.trim().toLowerCase();
    const found = q ? names.filter((n) => n.includes(q)) : names;
    return found.sort((a, b) => Number(b.startsWith(q)) - Number(a.startsWith(q)) || a.localeCompare(b)).slice(0, 8);
  }, [names, value]);

  const choose = (name: string) => {
    onChange(name);
    setOpen(false);
  };

  return (
    <div className="picker">
      <label className="field__label" htmlFor={`${listId}-input`}>{label}</label>
      <input
        id={`${listId}-input`}
        className="input mono"
        value={value}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        onChange={(e) => { onChange(e.target.value); setOpen(true); setActive(0); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, matches.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
          else if (e.key === "Enter" && open && matches[active]) { e.preventDefault(); choose(matches[active]); }
          else if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && matches.length > 0 && (
        <ul className="picker__list" id={listId} role="listbox">
          {matches.map((n, i) => (
            <li key={n} role="option" aria-selected={i === active}
              className={i === active ? "picker__option picker__option--active" : "picker__option"}
              onMouseDown={(e) => { e.preventDefault(); choose(n); }}
              onMouseEnter={() => setActive(i)}>
              <span className="mono">{n}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
