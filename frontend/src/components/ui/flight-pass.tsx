import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Badge, type Tone } from "./badge";
import { Icon } from "./icon";
import type { IconName } from "./icon-paths";

export interface PassEnd {
  iata: string;
  city: string;
  time: string;
  /** «UTC+1»: desfase de la ciudad (IU-05). */
  tz?: string;
}

export interface FlightPassProps {
  from: PassEnd;
  to: PassEnd;
  duration?: string;
  code: string;
  price: string;
  /** Precio sin descuento: activa el estilo de promoción. */
  oldPrice?: string;
  priceNote?: string;
  date?: string;
  note?: ReactNode;
  badges?: { tone?: Tone; icon?: IconName; label: string }[];
  action?: ReactNode;
  state?: "default" | "selected" | "soldout";
  className?: string;
}

function Extremo({ end, destino }: { end: PassEnd; destino?: boolean }) {
  return (
    <div className={cn("sta-pass__end", destino && "sta-pass__end--to")}>
      <span className="sta-pass__iata">{end.iata}</span>
      <span className="sta-pass__city">{end.tz ? `${end.city} · ${end.tz}` : end.city}</span>
      <span className="sta-pass__time">{end.time}</span>
    </div>
  );
}

/** El vuelo como pasabordo con talón (DESIGN.md › FlightPass). Horas en la hora local de cada
 *  ciudad (IU-05). `selected` y `soldout` llevan además un badge con palabra. */
export function FlightPass({
  from,
  to,
  duration = "Directo",
  code,
  price,
  oldPrice,
  priceNote,
  date,
  note,
  badges = [],
  action,
  state = "default",
  className,
}: FlightPassProps) {
  return (
    <article
      className={cn(
        "sta-pass",
        state === "selected" && "sta-pass--selected",
        state === "soldout" && "sta-pass--soldout",
        oldPrice && "sta-pass--promo",
        className,
      )}
      aria-label={`Vuelo ${code} ${from.city} a ${to.city}`}
    >
      <div className="sta-pass__grid">
        <div className="sta-pass__main">
          <div className="sta-pass__route">
            <Extremo end={from} />
            <div className="sta-pass__line">
              <div className="sta-pass__track">
                <Icon name="plane" />
              </div>
              <span className="sta-pass__dur">{duration}</span>
            </div>
            <Extremo end={to} destino />
          </div>
          {(badges.length > 0 || note || date) && (
            <div className="sta-pass__meta">
              {date && <span>{date}</span>}
              {badges.map((b) => (
                <Badge key={b.label} tone={b.tone} icon={b.icon}>
                  {b.label}
                </Badge>
              ))}
              {note && <span>{note}</span>}
            </div>
          )}
        </div>
        <div className="sta-pass__stub">
          <div>
            <div className="sta-pass__code">{code}</div>
            {oldPrice && <div className="sta-pass__old">{oldPrice}</div>}
            <div className="sta-pass__price">{price}</div>
            {priceNote && <div className="sta-pass__note">{priceNote}</div>}
          </div>
          {action}
        </div>
      </div>
    </article>
  );
}
