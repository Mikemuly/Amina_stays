"use client";

import { Globe, MessageSquare, Phone, Smartphone } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Badge } from "@/components/ui/misc";
import { CHANNEL_LABEL, STATUS_TONE } from "@/lib/format";
import { cn } from "@/lib/utils";

export function PageHeader({ title, subtitle, actions, back }: { title: React.ReactNode; subtitle?: React.ReactNode; actions?: React.ReactNode; back?: { href: string; label: string } }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {back && (
          <Link href={back.href} className="mb-2 inline-block text-[13px] font-semibold text-ink-2 hover:text-ink">
            ← {back.label}
          </Link>
        )}
        <h1 className="text-[26px] leading-tight font-semibold tracking-tight [overflow-wrap:anywhere] md:text-[32px]">{title}</h1>
        {subtitle && <p className="mt-1.5 text-base text-ink-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex max-w-full min-w-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Section({ title, action, children, className, padded = true }: { title?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode; className?: string; padded?: boolean }) {
  return (
    <section className={cn("rounded-2xl border border-line bg-white", className)}>
      {(title || action) && (
        <div className="flex items-center justify-between gap-3 border-b border-line-soft px-5 py-4">
          <h2 className="text-base font-semibold">{title}</h2>
          {action}
        </div>
      )}
      <div className={padded ? "p-5" : ""}>{children}</div>
    </section>
  );
}

export function KpiCard({ label, value, hint, delta, icon, tone = "neutral" }: {
  label: string; value: React.ReactNode; hint?: React.ReactNode; delta?: number | null; icon?: React.ReactNode; tone?: "neutral" | "brand" | "ocean";
}) {
  return (
    <div className="rounded-2xl border border-line bg-white p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-ink-2">{label}</p>
        {icon && (
          <span className={cn("grid size-8 place-items-center rounded-full", tone === "brand" ? "bg-brand-50 text-brand-600" : tone === "ocean" ? "bg-ocean-50 text-ocean-600" : "bg-surface text-ink-2")}>
            {icon}
          </span>
        )}
      </div>
      <p className="mt-2 text-[26px] leading-none font-semibold tracking-tight tabular-nums">{value}</p>
      <div className="mt-2 flex items-center gap-2 text-[13px] text-ink-2">
        {delta !== undefined && delta !== null && (
          <span className={cn("font-semibold", delta >= 0 ? "text-success" : "text-danger")}>
            {delta >= 0 ? "▲" : "▼"} {Math.abs(delta)}%
          </span>
        )}
        {hint}
      </div>
    </div>
  );
}

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  return (
    <Badge tone={STATUS_TONE[status] ?? "neutral"} dot>
      {label ?? status.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())}
    </Badge>
  );
}

const CHANNEL_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  web: Globe, ussd: Smartphone, sms: MessageSquare, voice: Phone, whatsapp: MessageSquare,
};

export function ChannelBadge({ channel, className }: { channel: string; className?: string }) {
  const Icon = CHANNEL_ICON[channel] ?? Globe;
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full border border-line-soft bg-white px-2 py-0.5 text-xs font-semibold text-ink-2", className)}>
      <Icon className="size-3.5" />
      {CHANNEL_LABEL[channel] ?? channel}
    </span>
  );
}

export function Table({ head, children, className, empty }: { head: React.ReactNode[]; children: React.ReactNode; className?: string; empty?: React.ReactNode }) {
  const rows = React.Children.count(children);
  return (
    <div className={cn("overflow-x-auto", className)}>
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead>
          <tr className="border-b border-line-soft text-xs font-medium text-ink-2">
            {head.map((h, i) => (
              <th key={i} className="px-4 py-3 whitespace-nowrap first:pl-5 last:pr-5">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line-soft">{children}</tbody>
      </table>
      {rows === 0 && empty && <div className="px-5 py-10 text-center text-sm text-ink-2">{empty}</div>}
    </div>
  );
}

export function Td({ className, children, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={cn("px-4 py-3 align-middle first:pl-5 last:pr-5", className)} {...props}>
      {children}
    </td>
  );
}

export function Tr({ className, onClick, children }: { className?: string; onClick?: () => void; children: React.ReactNode }) {
  return (
    <tr onClick={onClick} className={cn(onClick && "cursor-pointer transition-colors hover:bg-surface", className)}>
      {children}
    </tr>
  );
}

export function LoadingBlock({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-14 animate-pulse rounded-xl bg-surface" />
      ))}
    </div>
  );
}

export function ErrorBlock({ error, retry }: { error: unknown; retry?: () => void }) {
  return (
    <div className="rounded-2xl border border-danger/30 bg-danger-50 p-5 text-sm text-danger">
      {(error as Error)?.message ?? "Something went wrong."}
      {retry && (
        <button onClick={retry} className="ml-3 font-semibold underline">
          Try again
        </button>
      )}
    </div>
  );
}

export function KeyValue({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2 text-sm">
      <span className="text-ink-2">{label}</span>
      <span className="text-right font-medium">{children}</span>
    </div>
  );
}
