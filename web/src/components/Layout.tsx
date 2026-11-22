import { Link, NavLink, Outlet, useNavigation } from "react-router";
import { Plus } from "lucide-react";
import { cx } from "./ui";

export function Logo() {
  return (
    <Link
      to="/"
      className="flex items-center gap-2.5 rounded-lg focus-visible:outline-2 focus-visible:outline-amber-300"
    >
      <svg viewBox="0 0 32 32" className="size-8" aria-hidden>
        <rect width="32" height="32" rx="8" className="fill-zinc-900" />
        <rect
          x="11"
          y="5"
          width="10"
          height="22"
          rx="2.5"
          fill="none"
          stroke="#fbbf24"
          strokeWidth="2.5"
        />
        <path d="M14.5 13v6l5-3z" fill="#fbbf24" />
      </svg>
      <span className="text-lg font-semibold tracking-tight">clippers</span>
    </Link>
  );
}

export function Layout() {
  const navigation = useNavigation();
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-10 border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <div className="flex items-center gap-6">
            <Logo />
            <nav className="hidden sm:block">
              <NavLink
                to="/"
                end
                className={({ isActive }) =>
                  cx(
                    "rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                    isActive ? "text-white" : "text-zinc-400 hover:text-zinc-200",
                  )
                }
              >
                Jobs
              </NavLink>
            </nav>
          </div>
          <Link
            to="/new"
            className="inline-flex items-center gap-1.5 rounded-xl bg-amber-400 px-3.5 py-2 text-sm font-semibold text-zinc-950 transition hover:bg-amber-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-300"
          >
            <Plus aria-hidden className="size-4" />
            New clips
          </Link>
        </div>
        {navigation.state === "loading" && (
          <div aria-hidden className="h-0.5 w-full animate-pulse bg-amber-400/60" />
        )}
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
        <Outlet />
      </main>
    </div>
  );
}
