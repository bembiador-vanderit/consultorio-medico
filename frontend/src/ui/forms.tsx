import { createContext, forwardRef, useContext, useId, type InputHTMLAttributes, type SelectHTMLAttributes, type TextareaHTMLAttributes, type ReactNode } from "react";
import { cx } from "./primitives";

type FieldContextValue = { id: string; describedBy?: string; invalid: boolean; required?: boolean };
const FieldContext = createContext<FieldContextValue | null>(null);
type FieldProps = { id?: string; label: string; description?: string; error?: string; required?: boolean; requiredLabel?: string; children: ReactNode };

/** One control per FormField. Use a fieldset/FormSection for checkbox or radio groups. */
export function FormField({ id: explicitId, label, description, error, required, requiredLabel = "(obligatorio)", children }: FieldProps) {
  const generatedId = useId();
  const id = explicitId ?? generatedId;
  const describedBy = [description && `${id}-help`, error && `${id}-error`].filter(Boolean).join(" ") || undefined;
  return <FieldContext.Provider value={{ id, describedBy, invalid: Boolean(error), required }}>
    <div className="atlas-field"><label htmlFor={id} className="atlas-label">{label}{required && <span> {requiredLabel}</span>}</label>
      {children}{description && <p id={`${id}-help`} className="atlas-help">{description}</p>}
      {error && <p id={`${id}-error`} className="atlas-field-error">{error}</p>}
    </div>
  </FieldContext.Provider>;
}

function useFieldProps(props: { id?: string; "aria-describedby"?: string; "aria-invalid"?: InputHTMLAttributes<HTMLInputElement>["aria-invalid"]; required?: boolean }) {
  const field = useContext(FieldContext);
  return {
    id: field?.id ?? props.id,
    "aria-describedby": [field?.describedBy, props["aria-describedby"]].filter(Boolean).join(" ") || undefined,
    "aria-invalid": field?.invalid || props["aria-invalid"] || undefined,
    required: field?.required ?? props.required,
  };
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...props }, ref) {
  const field = useFieldProps(props);
  return <input {...props} {...field} ref={ref} className={cx("atlas-input", className)} />;
});
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...props }, ref) {
  const field = useFieldProps(props);
  return <textarea rows={4} {...props} {...field} ref={ref} className={cx("atlas-input", className)} />;
});
export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select({ className, ...props }, ref) {
  const field = useFieldProps(props);
  return <select {...props} {...field} ref={ref} className={cx("atlas-input", className)} />;
});

type ChoiceProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "children"> & { label: string };
function Choice({ label, type, className, ...props }: ChoiceProps & { type: "checkbox" | "radio" }) {
  const generatedId = useId();
  const id = props.id ?? generatedId;
  return <label htmlFor={id} className={cx("atlas-choice", className)}><input {...props} id={id} type={type} /><span>{label}</span></label>;
}
export function Checkbox(props: ChoiceProps) { return <Choice {...props} type="checkbox" />; }
export function Radio(props: ChoiceProps) { return <Choice {...props} type="radio" />; }
export function FormSection({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return <fieldset className="atlas-form-section"><legend className="atlas-card-title">{title}</legend>{description && <p className="atlas-help">{description}</p>}<div className="atlas-form-grid">{children}</div></fieldset>;
}
