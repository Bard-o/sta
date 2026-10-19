import type { ButtonHTMLAttributes, Ref } from "react";
import { Slot } from "radix-ui";
import { Link } from "react-router";
import { cn } from "@/lib/utils";
import { Icon } from "./icon";
import type { IconName } from "./icon-paths";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** `primary` (amarillo) solo para la acción por la que existe la vista: una por vista. */
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "md" | "sm";
  icon?: IconName;
  iconAfter?: IconName;
  block?: boolean;
  /** Ruta interna: el botón se pinta como enlace de React Router. */
  href?: string;
  /** Como en shadcn/ui: pinta el hijo con las clases del botón. */
  asChild?: boolean;
  ref?: Ref<HTMLButtonElement>;
}

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  iconAfter,
  block,
  href,
  asChild,
  className,
  children,
  type = "button",
  ...props
}: ButtonProps) {
  const clases = cn(
    "sta-btn",
    `sta-btn--${variant}`,
    size === "sm" && "sta-btn--sm",
    block && "sta-btn--block",
    className,
  );
  const contenido = (
    <>
      {icon && <Icon name={icon} />}
      {children}
      {iconAfter && <Icon name={iconAfter} />}
    </>
  );

  if (href) {
    return (
      <Link to={href} className={clases} aria-disabled={props.disabled || undefined}>
        {contenido}
      </Link>
    );
  }
  if (asChild) {
    return (
      <Slot.Root className={clases} {...props}>
        {children}
      </Slot.Root>
    );
  }
  return (
    <button type={type} className={clases} {...props}>
      {contenido}
    </button>
  );
}
