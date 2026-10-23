import type { MouseEventHandler, ReactNode } from "react";
import { Link, NavLink } from "react-router";
import { Icon } from "./icon";
import type { IconName } from "./icon-paths";

export interface NavItem {
  label: string;
  icon?: IconName;
  href: string;
  /** Si se omite, el item se marca activo cuando la ruta actual empieza por `href`. */
  active?: boolean;
  onClick?: MouseEventHandler;
}

export interface TopNavProps {
  items?: NavItem[];
  right?: ReactNode;
  user?: { name: string; role?: string; href?: string };
  homeHref?: string;
  brand?: string;
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase();
}

/** Avatar + nombre. Con `href` es un enlace (a «Mi perfil»). */
function UserChip({ user }: { user: NonNullable<TopNavProps["user"]> }) {
  const contenido = (
    <>
      <span className="sta-avatar" aria-hidden="true">
        {initials(user.name)}
      </span>
      <span>
        <span className="sta-user__name">{user.name}</span>
        {user.role && <span className="sta-user__role">{user.role}</span>}
      </span>
    </>
  );
  if (!user.href) return <div className="sta-user">{contenido}</div>;
  return (
    <Link className="sta-user" to={user.href} aria-label={`Mi perfil, ${user.name}`}>
      {contenido}
    </Link>
  );
}

/** La barra «letrero» (IU-02). El item activo es una píldora invert, no amarilla. */
export function TopNav({
  items = [],
  right,
  user,
  homeHref = "/",
  brand = "AVIANCO",
}: TopNavProps) {
  return (
    <header className="sta-nav">
      <Link className="sta-brand" to={homeHref} aria-label={`${brand}, inicio`}>
        {brand}
      </Link>
      <nav className="sta-nav__items" aria-label="Principal">
        {items.map((it) => (
          <NavLink
            key={it.href}
            to={it.href}
            className="sta-nav__item"
            onClick={it.onClick}
            aria-current={it.active === undefined ? undefined : it.active ? "page" : false}
          >
            {it.icon && <Icon name={it.icon} />}
            {it.label}
          </NavLink>
        ))}
      </nav>
      <div className="sta-nav__right">
        {right}
        {user && <UserChip user={user} />}
      </div>
    </header>
  );
}
