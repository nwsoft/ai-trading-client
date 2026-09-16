import type { ReactNode } from "react";

export type AppIconName = "blockchain" | "stock" | "portfolio" | "finance" | "analyst" | "manual" | "settings" | "power" | "record";

export function AppIcon({ name }: { name: AppIconName }) {
  const common = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  const shapes: Record<AppIconName, ReactNode> = {
    blockchain: <><circle cx="7" cy="12" r="3" /><circle cx="17" cy="7" r="3" /><circle cx="17" cy="17" r="3" /><path d="m9.7 10.5 4.6-2M9.7 13.5l4.6 2" /></>,
    stock: <><path d="M4 19V5M4 19h16" /><path d="m7 15 4-4 3 2 5-6" /></>,
    portfolio: <><circle cx="12" cy="12" r="8" /><path d="M12 4v8l5 3" /></>,
    finance: <><rect x="4" y="6" width="16" height="13" rx="2" /><path d="M4 10h16M8 4v4M16 4v4" /></>,
    analyst: <><path d="M4 18 9 12l4 3 7-9" /><path d="M16 6h4v4" /></>,
    manual: <><path d="M5 5.5A3.5 3.5 0 0 1 8.5 2H12v18H8.5A3.5 3.5 0 0 0 5 23z" /><path d="M19 5.5A3.5 3.5 0 0 0 15.5 2H12v18h3.5A3.5 3.5 0 0 1 19 23z" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4" /></>,
    power: <><path d="M12 3v9" /><path d="M7.1 5.7a8 8 0 1 0 9.8 0" /></>,
    record: <><circle cx="12" cy="12" r="8" /><path d="m9.5 9.5 5 5M14.5 9.5l-5 5" /></>,
  };
  return <svg aria-hidden="true" className="app-icon" viewBox="0 0 24 24" {...common}>{shapes[name]}</svg>;
}
