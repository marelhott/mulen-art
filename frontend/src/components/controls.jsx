import React from "react";

export function Label({ children }) {
  return <span className="control-label">{children}</span>;
}

export function IconButton({ label, children, ...props }) {
  return (
    <button
      type="button"
      className="icon-button"
      aria-label={label}
      title={label}
      {...props}
    >
      {children}
    </button>
  );
}

export function Select({ label, value, onChange, items }) {
  return (
    <label className="control-block">
      <Label>{label}</Label>
      <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}>
        {items.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
      </select>
    </label>
  );
}

export function Range({ label, value, min, max, step, onChange, hint }) {
  return (
    <label className="control-block range-field">
      <span className="label-row">
        <Label>{label}</Label>
        <output>
          {Number(value).toFixed(step < 0.1 ? 2 : step < 1 ? 1 : 0)}
        </output>
      </span>
      <input
        type="range"
        aria-label={label}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        style={{ "--range-fill": `${(100 * (value - min)) / (max - min)}%` }}
      />
      {hint && <span className="help-text">{hint}</span>}
    </label>
  );
}
