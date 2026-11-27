import { Loader2, Minus, Plus } from "lucide-react";
import * as React from "react";

import { cn, initials } from "@/lib/utils";

type Tone = "neutral" | "brand" | "ocean" | "success" | "warning" | "danger" | "dark";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface text-ink-2",
  brand: "bg-brand-50 text-brand-700",
  ocean: "bg-ocean-50 text-ocean-700",
  success: "bg-success-50 text-success",
  warning: "bg-warning-50 text-warning",
  danger: "bg-danger-50 text-danger",
  dark: "bg-ink text-white",
};

export function Badge({ tone = "neutral", className, children, dot }: { tone?: Tone; className?: string; children: React.ReactNode; dot?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap", TONES[tone], className)}>
      {dot && <span className="size-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-2xl border border-line-soft bg-white", className)} {...props} />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-lg bg-line-soft", className)} />;
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("size-5 animate-spin text-ink-2", className)} />;
}

export function Avatar({ name, src, size = 40, className }: { name?: string | null; src?: string; size?: number; className?: string }) {
  const palette = ["#0e8388", "#e8553e", "#7c3aed", "#b45309", "#0a7f3f", "#1d4ed8", "#be185d"];
  const color = palette[(name ?? "").split("").reduce((a, c) => a + c.charCodeAt(0), 0) % palette.length];
  return src ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt={name ?? ""} className={cn("rounded-full object-cover", className)} style={{ width: size, height: size }} />
  ) : (
    <span
      className={cn("grid shrink-0 place-items-center rounded-full font-semibold text-white", className)}
      style={{ width: size, height: size, background: color, fontSize: size * 0.38 }}
      aria-hidden
    >
      {initials(name)}
    </span>
  );
}

// aria-disabled rather than disabled: a button that disables itself drops focus, which closes the popover or sheet
// the stepper sits in on phones
export function Stepper({ value, min = 0, max = 16, onChange, label }: { value: number; min?: number; max?: number; onChange: (v: number) => void; label: string }) {
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        aria-label={`Fewer ${label}`}
        aria-disabled={value <= min}
        onClick={() => value > min && onChange(value - 1)}
        className="grid size-8 place-items-center rounded-full bg-chip text-ink transition-colors hover:bg-line-soft aria-disabled:cursor-not-allowed aria-disabled:bg-chip/60 aria-disabled:text-ink-disabled aria-disabled:hover:bg-chip/60"
      >
        <Minus className="size-3.5" strokeWidth={2.5} />
      </button>
      <span className="w-5 text-center text-base tabular-nums" aria-live="polite">{value}</span>
      <button
        type="button"
        aria-label={`More ${label}`}
        aria-disabled={value >= max}
        onClick={() => value < max && onChange(value + 1)}
        className="grid size-8 place-items-center rounded-full bg-chip text-ink transition-colors hover:bg-line-soft aria-disabled:cursor-not-allowed aria-disabled:bg-chip/60 aria-disabled:text-ink-disabled aria-disabled:hover:bg-chip/60"
      >
        <Plus className="size-3.5" strokeWidth={2.5} />
      </button>
    </div>
  );
}

export function EmptyState({ icon, title, children, action }: { icon?: React.ReactNode; title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-line-soft px-6 py-14 text-center">
      {icon && <div className="mb-4 grid size-12 place-items-center rounded-full bg-surface text-ink-2">{icon}</div>}
      <h3 className="text-lg font-semibold">{title}</h3>
      {children && <p className="mt-1.5 max-w-sm text-[15px] text-ink-2">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Divider({ className }: { className?: string }) {
  return <hr className={cn("border-line-soft", className)} />;
}

export function Stars({ rating, size = 14 }: { rating: number; size?: number }) {
  return (
    <span className="inline-flex gap-0.5" aria-label={`${rating} out of 5`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <svg key={i} viewBox="0 0 32 32" width={size} height={size} fill={i <= Math.round(rating) ? "#222" : "#ddd"} aria-hidden>
          <path d="M15.1 1.58l-4.13 8.88-9.86 1.27a1 1 0 0 0-.54 1.74l7.3 6.57-1.97 9.85a1 1 0 0 0 1.48 1.06l8.62-5 8.63 5a1 1 0 0 0 1.48-1.06l-1.97-9.85 7.3-6.57a1 1 0 0 0-.55-1.73l-9.86-1.28-4.12-8.88a1 1 0 0 0-1.82 0z" />
        </svg>
      ))}
    </span>
  );
}
