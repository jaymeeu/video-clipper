/** Small building blocks shared by the pages. */
import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Clock, Loader2, RotateCw, XCircle } from "lucide-react";
import type { JobState } from "../api/client";

export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(" ");
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 aria-hidden className={cx("animate-spin", className ?? "size-4")} />;
}

const STATUS: Record<JobState, { label: string; className: string; icon: ReactNode }> = {
  queued: {
    label: "Queued",
    className: "bg-zinc-800 text-zinc-300 ring-zinc-700",
    icon: <Clock aria-hidden className="size-3.5" />,
  },
  running: {
    label: "Working",
    className: "bg-amber-400/10 text-amber-300 ring-amber-400/30",
    icon: <Spinner className="size-3.5" />,
  },
  done: {
    label: "Ready",
    className: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/30",
    icon: <CheckCircle2 aria-hidden className="size-3.5" />,
  },
  failed: {
    label: "Failed",
    className: "bg-red-400/10 text-red-300 ring-red-400/30",
    icon: <XCircle aria-hidden className="size-3.5" />,
  },
};

export function StatusBadge({ state }: { state: JobState }) {
  const { label, className, icon } = STATUS[state];
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset",
        className,
      )}
    >
      {icon}
      {label}
    </span>
  );
}

export function ErrorPanel({
  title,
  message,
  onRetry,
  retryLabel = "Try again",
  busy = false,
}: {
  title: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  busy?: boolean;
}) {
  return (
    <div role="alert" className="rounded-2xl border border-red-500/30 bg-red-500/5 p-5">
      <div className="flex gap-3">
        <AlertTriangle aria-hidden className="mt-0.5 size-5 shrink-0 text-red-400" />
        <div className="min-w-0 flex-1">
          <p className="font-medium text-red-200">{title}</p>
          <p className="mt-1 break-words text-sm text-red-200/80">{message}</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              disabled={busy}
              className="mt-4 inline-flex items-center gap-2 rounded-lg bg-red-500/15 px-3 py-1.5 text-sm font-medium text-red-100 ring-1 ring-red-400/30 hover:bg-red-500/25 disabled:opacity-60"
            >
              {busy ? <Spinner /> : <RotateCw aria-hidden className="size-4" />}
              {retryLabel}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed border-zinc-800 px-6 py-16 text-center">
      <div className="rounded-2xl bg-zinc-900 p-4 text-amber-300 ring-1 ring-zinc-800">{icon}</div>
      <h2 className="mt-5 text-lg font-semibold">{title}</h2>
      <p className="mt-2 max-w-sm text-sm text-zinc-400">{children}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("animate-pulse rounded-lg bg-zinc-800/70", className)} />;
}

/** An on/off switch with a label and an explanation. */
export function Toggle({
  checked,
  onChange,
  label,
  description,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  description?: ReactNode;
}) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4">
      <span>
        <span className="block text-sm font-medium">{label}</span>
        {description && <span className="mt-0.5 block text-sm text-zinc-400">{description}</span>}
      </span>
      <span className="relative mt-0.5 inline-flex shrink-0">
        <input
          type="checkbox"
          role="switch"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="peer sr-only"
        />
        <span className="h-6 w-11 rounded-full bg-zinc-700 transition-colors peer-checked:bg-amber-400 peer-focus-visible:ring-2 peer-focus-visible:ring-amber-300 peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-zinc-900" />
        <span className="pointer-events-none absolute top-1 left-1 size-4 rounded-full bg-white shadow transition-transform peer-checked:translate-x-5" />
      </span>
    </label>
  );
}

/** A row of mutually exclusive choices (a styled radio group). */
export function Segmented<T extends string | number>({
  name,
  value,
  options,
  onChange,
}: {
  name: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={name}
      className="inline-flex rounded-xl bg-zinc-950 p-1 ring-1 ring-zinc-800"
    >
      {options.map((option) => (
        <label
          key={String(option.value)}
          className={cx(
            "cursor-pointer rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-amber-300",
            option.value === value
              ? "bg-zinc-800 text-white shadow-sm"
              : "text-zinc-400 hover:text-zinc-200",
          )}
        >
          <input
            type="radio"
            name={name}
            className="sr-only"
            checked={option.value === value}
            onChange={() => onChange(option.value)}
          />
          {option.label}
        </label>
      ))}
    </div>
  );
}
