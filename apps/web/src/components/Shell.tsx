"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import {
  BarChart3,
  CalendarDays,
  Clapperboard,
  FolderOpen,
  LayoutDashboard,
  Library,
  Menu,
  Palette,
  Plus,
  Settings,
  X,
} from "lucide-react";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/projects/new", label: "New Project", icon: Plus },
  { href: "/projects", label: "My Projects", icon: FolderOpen },
  { href: "/clips", label: "Clip Library", icon: Library, milestone: 2 },
  { href: "/studio", label: "Editing Studio", icon: Clapperboard, milestone: 5 },
  { href: "/calendar", label: "Publishing Calendar", icon: CalendarDays, milestone: 7 },
  { href: "/analytics", label: "Analytics", icon: BarChart3, milestone: 7 },
  { href: "/presets", label: "Brand Presets", icon: Palette, milestone: 4 },
  { href: "/settings", label: "Settings", icon: Settings },
];

function isActive(path: string, href: string) {
  if (href === "/") return path === "/";
  if (href === "/projects") return path === "/projects" || (path.startsWith("/projects/") && path !== "/projects/new");
  return path === href || path.startsWith(href + "/");
}

function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2.5 px-2">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-accent to-[#ff3d6e] shadow-[0_0_24px_-6px_var(--color-accent)]">
        <svg viewBox="0 0 24 24" className="h-4.5 w-4.5" fill="none" stroke="#0a0b0d" strokeWidth="2.6" strokeLinecap="round">
          <path d="M8 5v14M16 5v14M4 9h4M16 15h4" />
        </svg>
      </span>
      <span className="text-[15px] font-semibold tracking-tight">
        CLIPFORGE <span className="text-accent">AI</span>
      </span>
    </Link>
  );
}

function NavList({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname();
  return (
    <nav className="flex flex-col gap-0.5">
      {NAV.map(({ href, label, icon: Icon, milestone }) => {
        const active = isActive(path, href);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            className={`group flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
              active ? "bg-surface-3 text-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink"
            }`}
          >
            <Icon className={`h-4 w-4 ${active ? "text-accent" : "text-muted group-hover:text-ink-2"}`} />
            <span className="flex-1">{label}</span>
            {milestone && (
              <span className="rounded border border-line px-1.5 py-px font-mono text-[10px] text-muted">M{milestone}</span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    // Lets browser tests wait until React has attached event handlers.
    document.documentElement.dataset.hydrated = "true";
  }, []);
  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col gap-6 border-r border-line bg-surface px-3 py-5 lg:flex">
        <Logo />
        <NavList />
        <p className="mt-auto px-3 text-[11px] leading-relaxed text-muted">
          Milestone 1 build. Sections tagged <span className="font-mono">M#</span> arrive in that milestone.
        </p>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-surface/90 px-4 py-3 backdrop-blur lg:hidden">
          <Logo />
          <button aria-label="Open menu" onClick={() => setOpen(true)} className="rounded-lg p-2 hover:bg-surface-2">
            <Menu className="h-5 w-5" />
          </button>
        </header>
        {open && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} />
            <div className="absolute inset-y-0 left-0 flex w-72 flex-col gap-6 bg-surface px-3 py-5">
              <div className="flex items-center justify-between">
                <Logo />
                <button aria-label="Close menu" onClick={() => setOpen(false)} className="rounded-lg p-2 hover:bg-surface-2">
                  <X className="h-5 w-5" />
                </button>
              </div>
              <NavList onNavigate={() => setOpen(false)} />
            </div>
          </div>
        )}
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-9">{children}</main>
      </div>
    </div>
  );
}
