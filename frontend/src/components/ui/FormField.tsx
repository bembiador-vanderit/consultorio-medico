import React from "react";

interface FormFieldProps extends React.HTMLAttributes<HTMLDivElement> {
  label?: string;
  error?: string;
  helperText?: string;
  required?: boolean;
  children: React.ReactNode;
  className?: string;
}

export function FormField({
  label,
  error,
  helperText,
  required = false,
  children,
  className = "",
  ...props
}: FormFieldProps) {
  return (
    <div className={`w-full ${className}`} {...props}>
      {label && (
        <label className="block mb-2 text-sm font-medium text-[var(--atlas-text-primary)]">
          {label}
          {required && <span className="text-[var(--atlas-danger)] ml-1">*</span>}
        </label>
      )}

      <div className="relative">{children}</div>

      {error && (
        <p className="mt-1 text-xs font-medium text-[var(--atlas-danger)]" role="alert">
          {error}
        </p>
      )}

      {helperText && !error && (
        <p className="mt-1 text-xs text-[var(--atlas-text-muted)]">{helperText}</p>
      )}
    </div>
  );
}

interface TextInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  error?: boolean;
}

export function TextInput({ error = false, className = "", ...props }: TextInputProps) {
  const baseClasses =
    "w-full px-3 py-2 rounded-[var(--radius-md)] border text-sm font-normal transition-colors duration-[var(--transition-normal)]";

  const normalState =
    "bg-white border-[var(--atlas-border)] text-[var(--atlas-text-primary)] placeholder-[var(--atlas-text-muted)]";

  const focusState =
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--atlas-focus-ring)] focus-visible:ring-offset-2 focus-visible:border-[var(--atlas-primary)]";

  const disabledState =
    "disabled:bg-[var(--atlas-disabled-bg)] disabled:border-[var(--atlas-border)] disabled:text-[var(--atlas-disabled-text)] disabled:cursor-not-allowed";

  const errorState = error
    ? "border-[var(--atlas-danger)] focus-visible:ring-[var(--atlas-danger)]"
    : "";

  return (
    <input
      className={`${baseClasses} ${normalState} ${focusState} ${disabledState} ${errorState} ${className}`}
      {...props}
    />
  );
}

interface TextAreaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: boolean;
}

export function TextArea({ error = false, className = "", ...props }: TextAreaProps) {
  const baseClasses =
    "w-full px-3 py-2 rounded-[var(--radius-md)] border text-sm font-normal transition-colors duration-[var(--transition-normal)] resize-none";

  const normalState =
    "bg-white border-[var(--atlas-border)] text-[var(--atlas-text-primary)] placeholder-[var(--atlas-text-muted)]";

  const focusState =
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--atlas-focus-ring)] focus-visible:ring-offset-2 focus-visible:border-[var(--atlas-primary)]";

  const disabledState =
    "disabled:bg-[var(--atlas-disabled-bg)] disabled:border-[var(--atlas-border)] disabled:text-[var(--atlas-disabled-text)] disabled:cursor-not-allowed";

  const errorState = error
    ? "border-[var(--atlas-danger)] focus-visible:ring-[var(--atlas-danger)]"
    : "";

  return (
    <textarea
      className={`${baseClasses} ${normalState} ${focusState} ${disabledState} ${errorState} ${className}`}
      {...props}
    />
  );
}

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  error?: boolean;
  options: Array<{ value: string; label: string }>;
}

export function Select({ error = false, options = [], className = "", ...props }: SelectProps) {
  const baseClasses =
    "w-full px-3 py-2 rounded-[var(--radius-md)] border text-sm font-normal transition-colors duration-[var(--transition-normal)] appearance-none cursor-pointer";

  const normalState =
    "bg-white border-[var(--atlas-border)] text-[var(--atlas-text-primary)]";

  const focusState =
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--atlas-focus-ring)] focus-visible:ring-offset-2 focus-visible:border-[var(--atlas-primary)]";

  const disabledState =
    "disabled:bg-[var(--atlas-disabled-bg)] disabled:border-[var(--atlas-border)] disabled:text-[var(--atlas-disabled-text)] disabled:cursor-not-allowed";

  const errorState = error
    ? "border-[var(--atlas-danger)] focus-visible:ring-[var(--atlas-danger)]"
    : "";

  const backgroundImage = `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath fill='%23334E5A' d='M1 1l5 5 5-5'/%3E%3C/svg%3E")`;

  return (
    <select
      style={{
        backgroundImage,
        backgroundRepeat: "no-repeat",
        backgroundPosition: "right 10px center",
        paddingRight: "2.5rem",
      }}
      className={`${baseClasses} ${normalState} ${focusState} ${disabledState} ${errorState} ${className}`}
      {...props}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

interface CheckboxProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export function Checkbox({ label, className = "", ...props }: CheckboxProps) {
  const baseClasses =
    "h-4 w-4 rounded-[var(--radius-sm)] border border-[var(--atlas-border)] cursor-pointer accent-[var(--atlas-primary)] transition-colors duration-[var(--transition-normal)]";

  const focusState =
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--atlas-focus-ring)] focus-visible:ring-offset-2";

  const disabledState =
    "disabled:bg-[var(--atlas-disabled-bg)] disabled:border-[var(--atlas-disabled)] disabled:cursor-not-allowed";

  return (
    <div className="flex items-center gap-2">
      <input
        type="checkbox"
        className={`${baseClasses} ${focusState} ${disabledState} ${className}`}
        {...props}
      />
      {label && (
        <label className="text-sm font-medium text-[var(--atlas-text-primary)] cursor-pointer">
          {label}
        </label>
      )}
    </div>
  );
}
