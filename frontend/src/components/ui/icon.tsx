import { cn } from "@/lib/utils";
import { ICON_PATHS, type IconName } from "./icon-paths";

export interface IconProps {
  name: IconName;
  size?: "sm" | "lg";
  /** Si el ícono va solo y significa algo; si no, queda oculto para lectores de pantalla. */
  label?: string;
  className?: string;
}

export function Icon({ name, size, label, className }: IconProps) {
  return (
    <svg
      className={cn("sta-icon", size && `sta-icon--${size}`, className)}
      viewBox="0 0 24 24"
      aria-hidden={label ? undefined : true}
      role={label ? "img" : undefined}
      aria-label={label}
    >
      {ICON_PATHS[name].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
