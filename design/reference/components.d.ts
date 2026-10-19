import type * as React from 'react';

export type IconName = 'search' | 'plane' | 'calendar' | 'wallet' | 'ticket' | 'message' | 'user' | 'cart' | 'chevron-down' | 'chevron-right' | 'info' | 'x' | 'check' | 'arrow-up' | 'arrow-down' | 'arrow-right' | 'sliders' | 'bell' | 'plus' | 'alert' | 'news' | 'card' | 'tag' | 'list' | 'check-circle';
export type Tone = 'neutral' | 'accent' | 'success' | 'danger' | 'info';

export interface BackdropProps extends React.HTMLAttributes<HTMLDivElement> { /** URL de una foto real; se oscurece con `scrim`. */ image?: string }
export declare function Backdrop(props: BackdropProps): React.ReactElement;

export interface ShellProps { nav?: React.ReactNode; children?: React.ReactNode; /** false oculta el botón Información (admin, root). */ chat?: boolean; className?: string; style?: React.CSSProperties }
export declare function Shell(props: ShellProps): React.ReactElement;

export interface NavItem { label: string; icon?: IconName; href?: string; active?: boolean; onClick?: React.MouseEventHandler }
export interface TopNavProps { items?: NavItem[]; right?: React.ReactNode; user?: { name: string; role?: string }; homeHref?: string }
export declare function TopNav(props: TopNavProps): React.ReactElement;

export interface GlassProps extends React.HTMLAttributes<HTMLElement> { variant?: 'base' | 'strong' | 'inset'; padded?: boolean; as?: keyof JSX.IntrinsicElements; title?: React.ReactNode; actions?: React.ReactNode }
export declare function Glass(props: GlassProps): React.ReactElement;

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> { variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; size?: 'md' | 'sm'; icon?: IconName; iconAfter?: IconName; block?: boolean; href?: string }
export declare function Button(props: ButtonProps): React.ReactElement;

export interface BadgeProps { tone?: Tone; icon?: IconName; children?: React.ReactNode; className?: string }
export declare function Badge(props: BadgeProps): React.ReactElement;

export type SegOption = string | { value: string; label: React.ReactNode };
export interface SegmentedProps { options: SegOption[]; value?: string; defaultValue?: string; onChange?: (value: string) => void; label?: string; className?: string }
export declare function Segmented(props: SegmentedProps): React.ReactElement;

export interface FieldProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'value'> { label?: string; value?: string; hint?: React.ReactNode; error?: React.ReactNode; icon?: IconName; /** Si viene, el control es un select. */ options?: SegOption[] }
export declare function Field(props: FieldProps): React.ReactElement;

export interface SearchPillProps { placeholder?: string; value?: string; label?: string; onFilters?: (() => void) | false; className?: string; style?: React.CSSProperties }
export declare function SearchPill(props: SearchPillProps): React.ReactElement;

export interface StatTileProps { label: string; value: React.ReactNode; delta?: { dir: 'up' | 'down'; text: string; tone?: Tone }; foot?: React.ReactNode; action?: React.ReactNode; hero?: boolean; className?: string; style?: React.CSSProperties }
export declare function StatTile(props: StatTileProps): React.ReactElement;

export interface PassEnd { iata: string; city: string; time: string; /** «UTC+1» cuando la zona difiere de la del origen. */ tz?: string }
export interface FlightPassProps { from: PassEnd; to: PassEnd; duration?: string; code: string; price: string; oldPrice?: string; priceNote?: string; date?: string; note?: React.ReactNode; badges?: { tone?: Tone; icon?: IconName; label: string }[]; action?: React.ReactNode; state?: 'default' | 'selected' | 'soldout'; className?: string }
export declare function FlightPass(props: FlightPassProps): React.ReactElement;

export interface BoardColumn<R> { key: string; label: React.ReactNode; align?: 'left' | 'right'; render?: (row: R) => React.ReactNode }
export interface BoardProps<R = any> { columns: BoardColumn<R>[]; rows: R[]; highlight?: number; caption?: string }
export declare function Board<R = any>(props: BoardProps<R>): React.ReactElement;
export declare namespace Board { function Flap(props: { children?: React.ReactNode }): React.ReactElement }

export interface MeterProps { value: number; max: number }
export declare function Meter(props: MeterProps): React.ReactElement;

export interface SeatMapProps { current?: string; selected?: string | null; onSelect?: (code: string) => void; taken?: string[]; ticketClass?: 'economica' | 'primera'; firstRows?: number; rows?: number; fromRow?: number; toRow?: number; maxHeight?: number; footer?: React.ReactNode; className?: string }
export declare function SeatMap(props: SeatMapProps): React.ReactElement;
export declare namespace SeatMap { function Legend(): React.ReactElement }

export interface DialogProps { title: React.ReactNode; subtitle?: React.ReactNode; notice?: React.ReactNode; tone?: 'danger' | 'info'; children?: React.ReactNode; actions?: React.ReactNode; inline?: boolean }
export declare function Dialog(props: DialogProps): React.ReactElement;

export interface ChatFabProps { onClick?: () => void; label?: string; static?: boolean; className?: string; style?: React.CSSProperties }
export declare function ChatFab(props: ChatFabProps): React.ReactElement;

export interface IconProps { name: IconName; size?: 'sm' | 'lg'; label?: string; className?: string }
export declare function Icon(props: IconProps): React.ReactElement;

/** Pesos colombianos con punto de miles y sin decimales (IU-06). `sign` antepone «+ » o «− ». */
export declare function cop(n: number, opts?: { sign?: boolean }): string;

declare global {
  interface Window {
    STA: { Backdrop: typeof Backdrop; Shell: typeof Shell; TopNav: typeof TopNav; Glass: typeof Glass; Button: typeof Button; Badge: typeof Badge; Segmented: typeof Segmented; Field: typeof Field; SearchPill: typeof SearchPill; StatTile: typeof StatTile; FlightPass: typeof FlightPass; Board: typeof Board; Meter: typeof Meter; SeatMap: typeof SeatMap; Dialog: typeof Dialog; ChatFab: typeof ChatFab; Icon: typeof Icon; cop: typeof cop };
  }
}
