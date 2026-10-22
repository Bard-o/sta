import type { ComponentProps, ReactNode } from "react";
import { useFormContext, type FieldValues, type Path } from "react-hook-form";
import { FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "./form";
import { cop } from "@/lib/format";
import { Input } from "./input";
import { Select } from "./select";

type TextoProps<T extends FieldValues> = {
  name: Path<T>;
  label: string;
  className?: string;
  /** Ayuda bajo el campo; si hay error, se muestra el error en su lugar. */
  ayuda?: ReactNode;
} & Omit<ComponentProps<typeof Input>, "name">;

/** Etiqueta + campo de texto + ayuda/error, conectado al formulario de react-hook-form. Se usa
 *  dentro de `<Form>` indicando el tipo del formulario: `<CampoTexto<Datos> name="nombres" … />`. */
export function CampoTexto<T extends FieldValues>({
  name,
  label,
  className,
  ayuda,
  ...props
}: TextoProps<T>) {
  const { control } = useFormContext<T>();
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className={className}>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input {...props} {...field} value={String(field.value ?? "")} />
          </FormControl>
          {ayuda && <FormDescription>{ayuda}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

/** Lista desplegable conectada al formulario; `placeholder` agrega una opción vacía deshabilitada. */
export function CampoLista<T extends FieldValues>({
  name,
  label,
  opciones,
  placeholder,
}: {
  name: Path<T>;
  label: string;
  opciones: { value: string; label: string }[];
  placeholder?: string;
}) {
  const { control } = useFormContext<T>();
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className="sta-field--select">
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Select {...field} value={String(field.value ?? "")}>
              {placeholder && (
                <option value="" disabled>
                  {placeholder}
                </option>
              )}
              {opciones.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          </FormControl>
          <FormMessage />
        </FormItem>
      )}
    />
  );
}

/** Monto en pesos colombianos: se escribe con o sin puntos y al salir del campo queda como
 *  «$ 2.450.000» (IU-06). El valor del formulario es el texto; conviértelo con `soloDigitos`. */
export function CampoDinero<T extends FieldValues>({
  name,
  label,
  className,
  ayuda,
}: {
  name: Path<T>;
  label: string;
  className?: string;
  ayuda?: ReactNode;
}) {
  const { control } = useFormContext<T>();
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className={className}>
          <FormLabel>{label}</FormLabel>
          <FormControl>
            <Input
              inputMode="numeric"
              autoComplete="off"
              {...field}
              value={String(field.value ?? "")}
              onBlur={() => {
                field.onBlur();
                const monto = Number(String(field.value ?? "").replace(/\D/g, ""));
                if (monto > 0) field.onChange(cop(monto));
              }}
            />
          </FormControl>
          {ayuda && <FormDescription>{ayuda}</FormDescription>}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
