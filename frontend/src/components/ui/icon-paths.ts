// Trazos de los íconos del sistema de diseño (design/reference/components.reference.js).
// Varios siguen la geometría de Lucide (licencia ISC), ver DESIGN.md › Iconografía.
export const ICON_PATHS = {
  search: ["M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13z", "M20 20l-4.6-4.6"],
  plane: [
    "M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z",
  ],
  calendar: [
    "M5.5 5h13a2 2 0 0 1 2 2v11.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z",
    "M3.5 10h17",
    "M8 3v4",
    "M16 3v4",
  ],
  wallet: [
    "M4 7.5A2.5 2.5 0 0 1 6.5 5H18v2.5",
    "M6 7.5h12.5a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2.5 2.5 0 0 1-2.5-2.5V7.5",
    "M16 14.5h.01",
  ],
  ticket: [
    "M4 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v2.5a2.5 2.5 0 0 0 0 5V17a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-2.5a2.5 2.5 0 0 0 0-5z",
    "M14.5 5.5v2",
    "M14.5 11v2",
    "M14.5 16.5v2",
  ],
  message: [
    "M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 3.5V17H6.5A2.5 2.5 0 0 1 4 14.5z",
  ],
  user: ["M12 12a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z", "M5 20c1.2-3.5 4-5 7-5s5.8 1.5 7 5"],
  cart: [
    "M3 4h2.5l2.2 10.5a1.5 1.5 0 0 0 1.5 1.2h7.6a1.5 1.5 0 0 0 1.5-1.1L20 8H6.4",
    "M10 20h.01",
    "M17 20h.01",
  ],
  "chevron-down": ["M6 9l6 6 6-6"],
  "chevron-right": ["M9 6l6 6-6 6"],
  info: ["M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17z", "M12 11v5", "M12 7.8v.01"],
  x: ["M6 6l12 12", "M18 6L6 18"],
  check: ["M5 12.5l4.5 4.5L19 7.5"],
  "arrow-up": ["M12 19V5", "M6 11l6-6 6 6"],
  "arrow-down": ["M12 5v14", "M6 13l6 6 6-6"],
  "arrow-right": ["M5 12h14", "M13 6l6 6-6 6"],
  sliders: [
    "M4 7h9",
    "M19 7h1",
    "M4 17h2",
    "M12 17h8",
    "M16 9a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
    "M9 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4z",
  ],
  bell: ["M6 16v-5a6 6 0 1 1 12 0v5l1.5 2h-15z", "M10 20.5h4"],
  plus: ["M12 5v14", "M5 12h14"],
  alert: ["M12 4l9 16H3z", "M12 10v4", "M12 17v.01"],
  news: [
    "M6 4.5h12a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-11a2 2 0 0 1 2-2z",
    "M8 9h8",
    "M8 12.5h8",
    "M8 16h5",
  ],
  card: [
    "M5 6h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z",
    "M3 10h18",
    "M7 14.5h4",
  ],
  tag: ["M3.5 12.5V5A1.5 1.5 0 0 1 5 3.5h7.5l8 8-9 9z", "M8 8h.01"],
  list: ["M9 6h11", "M9 12h11", "M9 18h11", "M4.5 6h.01", "M4.5 12h.01", "M4.5 18h.01"],
  "check-circle": ["M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17z", "M8.5 12.5l2.5 2.5 4.5-5"],
} as const satisfies Record<string, readonly string[]>;

export type IconName = keyof typeof ICON_PATHS;
export const ICON_NAMES = Object.keys(ICON_PATHS) as IconName[];
