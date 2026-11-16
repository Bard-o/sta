import { useId, useState } from "react";
import { cn } from "@/lib/utils";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "./command";
import { Icon } from "./icon";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";

export type OpcionCombobox = { value: string; label: string };

type Props = {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  opciones: OpcionCombobox[];
  placeholder?: string;
  vacio?: string;
  cargando?: boolean;
  disabled?: boolean;
  invalido?: boolean;
  "aria-describedby"?: string;
  "aria-labelledby"?: string;
};

/** Lista desplegable con búsqueda (shadcn/ui sobre cmdk), pintada con `sta-input`.
 *
 *  Se usa cuando el catálogo tiene cientos de opciones y una lista nativa no alcanza: la persona
 *  escribe y ve solo las coincidencias. Con teclado funciona con flechas, Enter y Escape. */
export function Combobox({
  id,
  value,
  onChange,
  opciones,
  placeholder = "Elige una opción",
  vacio = "Sin resultados.",
  cargando = false,
  disabled = false,
  invalido = false,
  "aria-describedby": descritoPor,
  "aria-labelledby": etiquetadoPor,
}: Props) {
  const [abierto, setAbierto] = useState(false);
  const generado = useId();
  const listaId = `${id ?? generado}-lista`;
  const seleccion = opciones.find((opcion) => opcion.value === value);

  const elegir = (codigo: string) => {
    onChange(codigo);
    setAbierto(false);
  };

  return (
    <Popover open={abierto} onOpenChange={setAbierto}>
      <PopoverTrigger asChild>
        <button
          id={id}
          type="button"
          role="combobox"
          aria-expanded={abierto}
          aria-controls={abierto ? listaId : undefined}
          aria-haspopup="listbox"
          aria-invalid={invalido || undefined}
          aria-describedby={descritoPor}
          aria-labelledby={etiquetadoPor}
          disabled={disabled}
          className={cn(
            "sta-input flex items-center justify-between gap-2 text-left disabled:cursor-not-allowed disabled:opacity-50",
            invalido && "border-danger",
          )}
        >
          <span className={cn("truncate", !seleccion && "text-ink-faint")}>
            {seleccion?.label ?? placeholder}
          </span>
          <Icon name="chevron-down" className="text-ink-muted" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        id={listaId}
        className="p-0"
        style={{ width: "var(--radix-popover-trigger-width)" }}
      >
        <Command label="Buscar">
          <CommandInput placeholder="Busca…" aria-label="Buscar" />
          <CommandList>
            <CommandEmpty>{cargando ? "Cargando…" : vacio}</CommandEmpty>
            <CommandGroup>
              {opciones.map((opcion) => (
                <CommandItem key={opcion.value} onSelect={() => elegir(opcion.value)}>
                  <span className="truncate">{opcion.label}</span>
                  {opcion.value === value && <Icon name="check" className="text-accent" />}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
