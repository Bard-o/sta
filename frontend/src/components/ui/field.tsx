import { useId, type InputHTMLAttributes, type ReactNode, type Ref } from "react";
import { cn } from "@/lib/utils";
import { Icon } from "./icon";
import type { IconName } from "./icon-paths";

export type FieldOption = string | { value: string; label: ReactNode };

export interface FieldProps extends InputHTMLAttributes<HTMLInputElement & HTMLSelectElement> {
  label?: string;
  hint?: ReactNode;
  /** Qué está mal y cómo corregirlo, en español (IU-07). */
  error?: ReactNode;
  icon?: IconName;
  /** Si viene, el control es un select. */
  options?: FieldOption[];
  ref?: Ref<HTMLInputElement & HTMLSelectElement>;
}

/** Etiqueta + control + mensaje. Para formularios con validación, ver `form.tsx`. */
export function Field({ label, hint, error, icon, options, className, id, ...props }: FieldProps) {
  const autoId = useId();
  const controlId = id ?? autoId;
  const msgId = `${controlId}-m`;
  const msg = error ?? hint;
  const comunes = {
    id: controlId,
    className: "sta-input",
    "aria-invalid": error ? true : undefined,
    "aria-describedby": msg ? msgId : undefined,
  };

  return (
    <div
      className={cn(
        "sta-field",
        error && "sta-field--error",
        icon && "sta-field--icon",
        options && "sta-field--select",
        className,
      )}
    >
      {label && (
        <label className="sta-field__label" htmlFor={controlId}>
          {label}
        </label>
      )}
      <div className="sta-field__control">
        {icon && (
          <span className="sta-field__lead">
            <Icon name={icon} />
          </span>
        )}
        {options ? (
          <select {...props} {...comunes}>
            {options.map((o) => {
              const value = typeof o === "string" ? o : o.value;
              return (
                <option key={value} value={value}>
                  {typeof o === "string" ? o : o.label}
                </option>
              );
            })}
          </select>
        ) : (
          <input {...props} {...comunes} />
        )}
        {options && (
          <span className="sta-field__trail">
            <Icon name="chevron-down" />
          </span>
        )}
      </div>
      {msg && (
        <div className="sta-field__msg" id={msgId} role={error ? "alert" : undefined}>
          {error && <Icon name="alert" />}
          {msg}
        </div>
      )}
    </div>
  );
}
