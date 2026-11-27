"use client";

import {
  Building2, CalendarCheck, ClipboardCheck, Globe, Hash, House, KeyRound, LogIn, type LucideIcon, Megaphone, MessageCircle,
  MessageSquare, MessagesSquare, Phone, SearchCheck, Settings2, Shirt, ShoppingBasket, Siren, Sparkles, Star, Tag, UserRound, Users,
  Wallet, Wrench,
} from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Avatar, Badge } from "@/components/ui/misc";
import { Tooltip } from "@/components/ui/overlays";
import { kes } from "@/lib/format";
import { cn, flag } from "@/lib/utils";

import { countdown, countryName, displayName, fmtPhone, HOUSEKEEPING, relTime, useHostAction, useNow } from "./lib";

/** Keyframes used across the Operate pages (flash for live items, shake for a wrong keypad code). */
export function OpsKeyframes() {
  return (
    <style href="amina-ops-keyframes" precedence="default">{`
@keyframes ops-flash { 0% { background-color: var(--color-brand-50); } 100% { background-color: transparent; } }
@keyframes ops-in { 0% { opacity: 0; transform: translateY(-8px); } 100% { opacity: 1; transform: none; } }
@keyframes ops-shake { 10%, 90% { transform: translateX(-1px); } 20%, 80% { transform: translateX(2px); } 30%, 50%, 70% { transform: translateX(-5px); } 40%, 60% { transform: translateX(5px); } }
@keyframes ops-pop { 0% { transform: scale(.9); opacity: 0; } 60% { transform: scale(1.04); opacity: 1; } 100% { transform: scale(1); } }
`}</style>
  );
}

// ---------- channels & activity kinds ----------

export const CHANNEL_ICONS: Record<string, LucideIcon> = {
  web: Globe, ussd: Hash, sms: MessageSquare, voice: Phone, whatsapp: MessageCircle, walk_in: UserRound, airbnb: House, booking_com: Building2,
  console: Settings2,
};

export function ChannelIcon({ channel, className }: { channel: string; className?: string }) {
  const Icon = CHANNEL_ICONS[channel] ?? Globe;
  return <Icon className={className} aria-hidden />;
}

export const KIND_META: Record<string, { icon: LucideIcon; color: string; label: string }> = {
  sms: { icon: MessageSquare, color: "#e8553e", label: "SMS" },
  ussd: { icon: Hash, color: "#b45309", label: "USSD" },
  voice: { icon: Phone, color: "#7c3aed", label: "Voice" },
  web: { icon: Globe, color: "#0e8388", label: "Web" },
  whatsapp: { icon: MessageCircle, color: "#16a34a", label: "WhatsApp" },
  walk_in: { icon: UserRound, color: "#6a6a6a", label: "Walk-in" },
  airbnb: { icon: House, color: "#ff385c", label: "Airbnb" },
  booking_com: { icon: Building2, color: "#1e40af", label: "Booking.com" },
  payment: { icon: Wallet, color: "#0a7f3f", label: "Payment" },
  lock: { icon: KeyRound, color: "#222222", label: "Door lock" },
  task: { icon: ClipboardCheck, color: "#1d4ed8", label: "Task" },
  alert: { icon: Siren, color: "#c13515", label: "Alert" },
  booking: { icon: CalendarCheck, color: "#0b6e72", label: "Booking" },
  message: { icon: MessagesSquare, color: "#e8553e", label: "Message" },
  review: { icon: Star, color: "#b45309", label: "Review" },
  pricing: { icon: Tag, color: "#6a6a6a", label: "Pricing" },
  listing: { icon: House, color: "#6a6a6a", label: "Listing" },
  guest: { icon: Users, color: "#7c3aed", label: "Guest" },
  broadcast: { icon: Megaphone, color: "#e8553e", label: "Broadcast" },
  system: { icon: Settings2, color: "#6a6a6a", label: "System" },
  auth: { icon: LogIn, color: "#6a6a6a", label: "Login" },
};

/** Booking/message events carry the channel they came through; everything else is described by its kind. */
export function activityMeta(kind: string, channel: string) {
  const byChannel = ["booking", "message", "sms", "ussd", "voice"].includes(kind) && channel && KIND_META[channel];
  return byChannel || KIND_META[kind] || KIND_META[channel] || KIND_META.system;
}

export function KindBubble({ kind, channel = "", size = 36 }: { kind: string; channel?: string; size?: number }) {
  const meta = activityMeta(kind, channel);
  const Icon = meta.icon;
  return (
    <span
      className="grid shrink-0 place-items-center rounded-full"
      style={{ width: size, height: size, backgroundColor: `${meta.color}1a`, color: meta.color }}
      aria-hidden
    >
      <Icon className="size-[45%]" strokeWidth={2.2} />
    </span>
  );
}

// ---------- tasks ----------

export const TASK_TYPES: Record<string, { label: string; icon: LucideIcon; color: string }> = {
  turnover: { label: "Turnover clean", icon: Sparkles, color: "#0b6e72" },
  maintenance: { label: "Maintenance", icon: Wrench, color: "#b45309" },
  inspection: { label: "Inspection", icon: SearchCheck, color: "#1d4ed8" },
  laundry: { label: "Laundry", icon: Shirt, color: "#7c3aed" },
  restock: { label: "Restock", icon: ShoppingBasket, color: "#0a7f3f" },
  guest_request: { label: "Guest request", icon: MessageCircle, color: "#e8553e" },
  other: { label: "Other", icon: ClipboardCheck, color: "#6a6a6a" },
};

export function TaskTypeIcon({ type, size = 32 }: { type: string; size?: number }) {
  const meta = TASK_TYPES[type] ?? TASK_TYPES.other;
  const Icon = meta.icon;
  return (
    <span
      className="grid shrink-0 place-items-center rounded-lg"
      style={{ width: size, height: size, backgroundColor: `${meta.color}14`, color: meta.color }}
      title={meta.label}
      aria-hidden
    >
      <Icon className="size-[50%]" strokeWidth={2.1} />
    </span>
  );
}

export function PriorityChip({ priority, quiet = true }: { priority: string; quiet?: boolean }) {
  if (priority === "urgent") return <Badge tone="danger">Urgent</Badge>;
  if (priority === "high") return <Badge tone="warning">High</Badge>;
  if (quiet) return null;
  return <Badge tone="neutral">{priority === "low" ? "Low" : "Normal"}</Badge>;
}

// ---------- people ----------

export function Flag({ code, className }: { code?: string | null; className?: string }) {
  if (!code) return null;
  return (
    <span className={cn("leading-none", className)} title={countryName(code)} role="img" aria-label={countryName(code)}>
      {flag(code)}
    </span>
  );
}

/** Initials for named guests; a neutral person glyph for numbers we don't have a name for yet. */
export function GuestAvatar({ name, size = 40, className }: { name?: string | null; size?: number; className?: string }) {
  if (name?.trim()) return <Avatar name={name} size={size} className={className} />;
  return (
    <span
      className={cn("grid shrink-0 place-items-center rounded-full bg-surface text-ink-3 ring-1 ring-line-soft", className)}
      style={{ width: size, height: size }}
      aria-hidden
    >
      <UserRound style={{ width: size * 0.46, height: size * 0.46 }} />
    </span>
  );
}

export function GuestLine({
  name, phone, nationality, showPhone = false, className,
}: { name?: string | null; phone?: string | null; nationality?: string | null; showPhone?: boolean; className?: string }) {
  return (
    <span className={cn("block min-w-0", className)}>
      <span className="flex min-w-0 items-center gap-1.5">
        <span className="truncate font-semibold text-ink">{displayName(name, phone)}</span>
        <Flag code={nationality} className="text-[15px]" />
      </span>
      {showPhone && name && phone && <span className="block truncate text-[13px] text-ink-2 tabular-nums">{fmtPhone(phone)}</span>}
    </span>
  );
}

// ---------- time ----------

export function RelTime({ at, className }: { at?: string | null; className?: string }) {
  const now = useNow(15_000);
  if (!at) return null;
  return (
    <time dateTime={at} className={className} title={new Date(at).toLocaleString("en-KE")} suppressHydrationWarning>
      {relTime(at, now)}
    </time>
  );
}

export function Countdown({ to, className }: { to: string; className?: string }) {
  const now = useNow(1000);
  const left = now ? new Date(to).getTime() - now : 0;
  return (
    <span className={cn("font-semibold tabular-nums", left < 120_000 ? "text-danger" : "text-warning", className)} suppressHydrationWarning>
      {now ? (left > 0 ? countdown(left) : "expired") : "—"}
    </span>
  );
}

// ---------- chips ----------

export function HousekeepingDot({ status, className }: { status: string; className?: string }) {
  const meta = HOUSEKEEPING[status] ?? HOUSEKEEPING.clean;
  return (
    <Tooltip content={meta.label}>
      <span className={cn("inline-block size-2 shrink-0 rounded-full", meta.dot, className)} aria-label={meta.label} role="img" />
    </Tooltip>
  );
}

export function HousekeepingChip({ status }: { status: string }) {
  const meta = HOUSEKEEPING[status] ?? HOUSEKEEPING.clean;
  return (
    <Badge tone={meta.tone} dot>
      {meta.label}
    </Badge>
  );
}

export function RiskChip({ score, always = false }: { score: number; always?: boolean }) {
  if (!always && score < 40) return null;
  const tone = score >= 60 ? "danger" : score >= 40 ? "warning" : "success";
  return (
    <Badge tone={tone} className="tabular-nums">
      Risk {score}
    </Badge>
  );
}

export function BalanceChip({ balance, status }: { balance: number; status?: string }) {
  if (status === "cancelled" || status === "expired") return null;
  if (balance <= 0) return <Badge tone="success">Paid</Badge>;
  return (
    <Badge tone="warning" className="tabular-nums">
      {kes(balance)} due
    </Badge>
  );
}

export function CountPill({ n, tone = "neutral" }: { n: number; tone?: "neutral" | "brand" | "danger" }) {
  return (
    <span
      className={cn(
        "inline-flex min-w-6 items-center justify-center rounded-full px-1.5 text-xs leading-5 font-bold tabular-nums",
        tone === "brand" ? "bg-brand-500 text-white" : tone === "danger" ? "bg-danger text-white" : "bg-surface text-ink-2",
      )}
    >
      {n}
    </span>
  );
}

export function Segmented<T extends string | number>({
  value, onChange, options, label, size = "md",
}: { value: T; onChange: (v: T) => void; options: { value: T; label: React.ReactNode }[]; label: string; size?: "sm" | "md" }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-full border border-line bg-white p-0.5">
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={cn(
            "rounded-full font-semibold whitespace-nowrap transition-colors",
            size === "sm" ? "h-7 px-3 text-[13px]" : "h-8 px-3.5 text-[13px]",
            o.value === value ? "bg-ink text-white" : "text-ink-2 hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function MiniEmpty({ icon, title, children, className }: { icon?: React.ReactNode; title: string; children?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-4 py-8 text-center", className)}>
      {icon && <div className="mb-3 grid size-10 place-items-center rounded-full bg-surface text-ink-2 [&_svg]:size-[18px]">{icon}</div>}
      <p className="text-sm font-semibold">{title}</p>
      {children && <p className="mt-1 max-w-xs text-[13px] text-ink-2">{children}</p>}
    </div>
  );
}

export function Overline({ children, className }: { children: React.ReactNode; className?: string }) {
  return <p className={cn("text-[11px] font-bold tracking-wider text-ink-3 uppercase", className)}>{children}</p>;
}

// ---------- actions ----------

export function IconAction({
  label, icon: Icon, onClick, className, disabled,
}: { label: string; icon: LucideIcon; onClick?: () => void; className?: string; disabled?: boolean }) {
  return (
    <Tooltip content={label}>
      <Button type="button" variant="ghost" size="icon-sm" aria-label={label} onClick={onClick} disabled={disabled} className={cn("text-ink-2 hover:text-ink", className)}>
        <Icon className="size-4" />
      </Button>
    </Tooltip>
  );
}

/** A trigger + confirmation dialog + mutation, for one-shot actions like "Check out" or "Release code". */
export function ConfirmAction({
  trigger, title, children, confirmLabel, tone = "dark", run, success,
}: {
  trigger: (open: () => void) => React.ReactNode;
  title: string;
  children?: React.ReactNode;
  confirmLabel: string;
  tone?: "dark" | "danger";
  run: () => Promise<unknown>;
  success?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const action = useHostAction(run, { success, onSuccess: () => setOpen(false) });
  return (
    <>
      {trigger(() => setOpen(true))}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          size="sm"
          title={title}
          footer={
            <div className="flex justify-end gap-2">
              <DialogClose asChild>
                <Button variant="ghost">Not now</Button>
              </DialogClose>
              <Button variant={tone === "danger" ? "danger" : "dark"} loading={action.isPending} onClick={() => action.mutate()}>
                {confirmLabel}
              </Button>
            </div>
          }
        >
          <div className="px-6 py-5 text-[15px] leading-relaxed text-ink-2">{children}</div>
        </DialogContent>
      </Dialog>
    </>
  );
}
