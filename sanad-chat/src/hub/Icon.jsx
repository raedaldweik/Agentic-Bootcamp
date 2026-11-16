// One small stroke-icon set for the cards and controls.
const P = {
  engine: <><circle cx="12" cy="12" r="3.2" /><path d="M12 3v3.2M12 17.8V21M3 12h3.2M17.8 12H21M5.6 5.6l2.3 2.3M16.1 16.1l2.3 2.3M18.4 5.6l-2.3 2.3M7.9 16.1l-2.3 2.3" /></>,
  fan: <><circle cx="12" cy="12" r="2" /><path d="M12 10c-1-3 0-6 3-7 1 3 0 5-3 7zM14 12c3-1 6 0 7 3-3 1-5 0-7-3zM12 14c1 3 0 6-3 7-1-3 0-5 3-7zM10 12c-3 1-6 0-7-3 3-1 5 0 7 3z" /></>,
  check: <><circle cx="12" cy="12" r="9" /><path d="M8 12.5l2.8 2.8L16.5 9.5" /></>,
  alert: <><path d="M12 3.5l9.5 16.5h-19z" /><path d="M12 10v4.5M12 17.4v.1" /></>,
  x: <><circle cx="12" cy="12" r="9" /><path d="M9 9l6 6M15 9l-6 6" /></>,
  calendar: <><rect x="3.5" y="5" width="17" height="15.5" rx="2.5" /><path d="M3.5 10h17M8 3v4M16 3v4" /></>,
  clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5.2l3.4 2" /></>,
  box: <><path d="M3.5 7.5L12 3l8.5 4.5v9L12 21l-8.5-4.5z" /><path d="M3.5 7.5L12 12l8.5-4.5M12 12v9" /></>,
  plane: <><path d="M21 4L3 11l6.5 2.5L12 20l3-5.5z" /><path d="M9.5 13.5L21 4" /></>,
  wrench: <><path d="M14.5 6.5a4.5 4.5 0 005.9 5.9L21 13l-7.5 7.5a2.1 2.1 0 01-3-3L18 10l-.4-.4a4.5 4.5 0 01-5.9-5.9l2.8 2.8z" /></>,
  shield: <><path d="M12 3l7.5 3v5.5c0 4.6-3.1 8-7.5 9.5-4.4-1.5-7.5-4.9-7.5-9.5V6z" /><path d="M9 12l2.2 2.2L15.2 10" /></>,
  users: <><circle cx="9" cy="8.5" r="3.2" /><path d="M2.8 19.5c.6-3.3 3-5 6.2-5s5.6 1.7 6.2 5" /><path d="M16 5.6a3.2 3.2 0 010 5.8M18 14.8c1.9.6 3 2.2 3.3 4.7" /></>,
  layers: <><path d="M12 3.5l8.5 4.5L12 12.5 3.5 8z" /><path d="M3.5 12l8.5 4.5 8.5-4.5M3.5 16l8.5 4.5 8.5-4.5" /></>,
  coins: <><ellipse cx="9" cy="8" rx="5.5" ry="2.8" /><path d="M3.5 8v4c0 1.5 2.5 2.8 5.5 2.8M3.5 12v4c0 1.5 2.5 2.8 5.5 2.8" /><ellipse cx="15.5" cy="13.5" rx="5" ry="2.6" /><path d="M10.5 13.5v3.7c0 1.4 2.2 2.6 5 2.6s5-1.2 5-2.6v-3.7" /></>,
  route: <><circle cx="6" cy="18" r="2.5" /><circle cx="18" cy="6" r="2.5" /><path d="M8.5 18H15a3.5 3.5 0 000-7H9a3.5 3.5 0 010-7h6.5" /></>,
  doc: <><path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h6" /></>,
  camera: <><path d="M4 8h3.2l1.6-2.5h6.4L16.8 8H20a1.5 1.5 0 011.5 1.5v8A1.5 1.5 0 0120 19H4a1.5 1.5 0 01-1.5-1.5v-8A1.5 1.5 0 014 8z" /><circle cx="12" cy="13.2" r="3.3" /></>,
  pin: <><path d="M12 21s-6.5-5.6-6.5-10.5a6.5 6.5 0 0113 0C18.5 15.4 12 21 12 21z" /><circle cx="12" cy="10.5" r="2.3" /></>,
  target: <><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /><circle cx="12" cy="12" r="1.2" /></>,
  gear: <><circle cx="12" cy="12" r="3" /><path d="M19.4 13.5a7.6 7.6 0 000-3l2-1.5-2-3.5-2.4 1a7.6 7.6 0 00-2.6-1.5L14 2.5h-4l-.400 2.5A7.6 7.6 0 007 6.5l-2.4-1-2 3.5 2 1.5a7.6 7.6 0 000 3l-2 1.5 2 3.5 2.4-1a7.6 7.6 0 002.6 1.5l.400 2.5h4l.400-2.5a7.6 7.6 0 002.6-1.5l2.4 1 2-3.5z" /></>,
  clipboard: <><rect x="5" y="4.5" width="14" height="16.5" rx="2" /><path d="M9 4.5V3h6v1.5M9 11h6M9 15h4" /></>,
  branch: <><circle cx="6" cy="5.5" r="2.3" /><circle cx="6" cy="18.5" r="2.3" /><circle cx="18" cy="8.5" r="2.3" /><path d="M6 7.8v8.4M18 10.8c0 3.2-3 4.2-6 4.2H9" /></>,
  mic: <><path d="M12 2.5a3 3 0 00-3 3v6a3 3 0 006 0v-6a3 3 0 00-3-3z" /><path d="M18.5 10.5v1a6.5 6.5 0 01-13 0v-1M12 18v3.5M8.5 21.5h7" /></>,
  speaker: <><path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z" /><path d="M15.5 9a4.2 4.2 0 010 6M18 6.5a8 8 0 010 11" /></>,
  mute: <><path d="M4 9.5v5h3.5L12 18.5v-13L7.5 9.5z" /><path d="M16 9.5l5 5M21 9.5l-5 5" /></>,
  book: <><path d="M4.5 4.5h6a2.5 2.5 0 012.5 2.5v13a2 2 0 00-2-2h-6.5z" /><path d="M19.5 4.5h-4A2.5 2.5 0 0013 7v13a2 2 0 012-2h4.5z" /></>,
  bookmark: <><path d="M6.5 3.5h11v17l-5.5-4-5.5 4z" /></>,
  send: <><path d="M21 3L10.5 13.5M21 3l-6.5 18-4-8-8-4z" /></>,
  stop: <><rect x="6.5" y="6.5" width="11" height="11" rx="2" /></>,
  chevron: <><path d="M6 9l6 6 6-6" /></>,
  menu: <><path d="M4 7h16M4 12h16M4 17h16" /></>,
  attach: <><path d="M21 11l-9 9a5.7 5.7 0 01-8-8l9-9a3.8 3.8 0 015.4 5.4L9.7 17a1.9 1.9 0 01-2.7-2.7l8-8" /></>,
  grid: <><rect x="3.5" y="3.5" width="7" height="7" rx="1.2" /><rect x="13.5" y="3.5" width="7" height="7" rx="1.2" /><rect x="3.5" y="13.5" width="7" height="7" rx="1.2" /><rect x="13.5" y="13.5" width="7" height="7" rx="1.2" /></>,
  trash: <><path d="M4.5 6.5h15M9.5 6.5V4h5v2.5M6.5 6.5l1 14h9l1-14M10 10.5v6M14 10.5v6" /></>,
  bolt: <><path d="M13 2.5L4.5 13.5H11l-1 8L19.5 10H13z" /></>,
  close: <><path d="M6 6l12 12M18 6L6 18" /></>,
  user: <><circle cx="12" cy="8" r="3.8" /><path d="M4.5 20.5c.8-4 3.7-6 7.5-6s6.7 2 7.5 6" /></>,
};

export default function Icon({ name, size = 16, stroke = 1.8, className = '', style }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke}
      strokeLinecap="round" strokeLinejoin="round" className={className} style={style} aria-hidden="true">
      {P[name] || P.doc}
    </svg>
  );
}
