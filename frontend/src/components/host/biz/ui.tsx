"use client";

import { ArrowDown, ArrowUp, Check, CircleAlert, Copy, Info, Plus, ShieldCheck, TriangleAlert, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { Badge } from "@/components/ui/misc";
import { Switch, Tooltip } from "@/components/ui/overlays";
import { ApiError } from "@/lib/api";
import { ago, plural } from "@/lib/format";
import { COUNTRIES, cn, flag } from "@/lib/utils";

import { describeChar, smsInfo, toGsm } from "./sms";

// ---------- small helpers ----------

export const reservationHref = (ref: string) => `/host/reservations?ref=${encodeURIComponent(ref)}`;

export const humanize = (s?: string | null) => (s ? s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()) : "");

export function countryName(code?: string | null) {
  if (!code) return "";
  return COUNTRIES.find(([c]) => c === code.toUpperCase())?.[1] ?? code.toUpperCase();
}

export function pctChange(cur: number | null | undefined, prev: number | null | undefined) {
  if (cur == null || prev == null || prev === 0) return null;
  return Math.round(((cur - prev) / Math.abs(prev)) * 100);
}

export const compactKes = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M` : n >= 1000 ? `${Math.round(n / 1000)}k` : String(Math.round(n));

/** "just now" for the last ~minute, otherwise "5 minutes ago". */
export function since(d?: string | null) {
  if (!d) return "";
  return new Date().getTime() - new Date(d).getTime() < 60_000 ? "just now" : ago(d);
}

export const HOURS = Array.from({ length: 24 }, (_, h) => ({ value: h, label: `${String(h).padStart(2, "0")}:00` }));

export function errorMessage(e: unknown, fallback = "Something went wrong.") {
  return e instanceof Error && e.message ? e.message : fallback;
}

function firstMessage(v: unknown): string {
  if (Array.isArray(v)) return v.map(firstMessage).find(Boolean) ?? "";
  if (v && typeof v === "object") return Object.values(v).map(firstMessage).find(Boolean) ?? "";
  return v == null ? "" : String(v);
}

/** Field → message map from a DRF validation error ({error, details: {field: [msg]}}). */
export function fieldErrors(e: unknown): Record<string, string> {
  if (!(e instanceof ApiError) || !e.data || typeof e.data !== "object") return {};
  const details = (e.data as { details?: unknown }).details;
  if (!details || typeof details !== "object" || Array.isArray(details)) return {};
  return Object.fromEntries(Object.entries(details).map(([k, v]) => [k, firstMessage(v)]));
}

export function useDebounced<T>(value: T, ms = 300) {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

/** Tab state mirrored into ?tab= (shallow — no server round trip). Needs a Suspense boundary above it. */
export function useTabParam<T extends string>(tabs: readonly T[], fallback: T, param = "tab") {
  const sp = useSearchParams();
  const raw = sp.get(param);
  const tab = raw && (tabs as readonly string[]).includes(raw) ? (raw as T) : fallback;
  const setTab = React.useCallback(
    (next: string) => {
      const url = new URL(window.location.href);
      if (next === fallback) url.searchParams.delete(param);
      else url.searchParams.set(param, next);
      window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    },
    [fallback, param],
  );
  return [tab, setTab] as const;
}

/** Shallow-update several query params at once (call from event handlers only). */
export function replaceSearchParams(patch: Record<string, string | null>) {
  const url = new URL(window.location.href);
  for (const [k, v] of Object.entries(patch)) {
    if (v === null) url.searchParams.delete(k);
    else url.searchParams.set(k, v);
  }
  window.history.replaceState(null, "", url.pathname + url.search + url.hash);
}

/** Warn before leaving the page with unsaved edits, and save on ⌘S / Ctrl+S. */
export function useUnsavedChanges(dirty: boolean, onSave?: () => void) {
  const save = React.useEffectEvent(() => onSave?.());
  React.useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    const keydown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        save();
      }
    };
    window.addEventListener("beforeunload", beforeUnload);
    window.addEventListener("keydown", keydown);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      window.removeEventListener("keydown", keydown);
    };
  }, [dirty]);
}

export function isEqualJson(a: unknown, b: unknown) {
  return JSON.stringify(a) === JSON.stringify(b);
}

// ---------- CSV export ----------

const csvCell = (v: unknown) => {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export const toCsv = (rows: unknown[][]) => "\ufeff" + rows.map((r) => r.map(csvCell).join(",")).join("\r\n");

function saveBlob(blob: Blob, filename: string) {
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 2000);
}

/** Download the server's CSV export; if that endpoint fails, build the same file from data already on screen. */
export async function downloadCsv(url: string, filename: string, fallback: () => string) {
  try {
    const res = await fetch(url, { credentials: "same-origin" });
    if (res.ok && (res.headers.get("content-type") ?? "").includes("text/csv")) {
      saveBlob(await res.blob(), filename);
      return;
    }
  } catch {
    // fall back to the client-side copy below
  }
  saveBlob(new Blob([fallback()], { type: "text/csv;charset=utf-8" }), filename);
}

// ---------- layout pieces ----------

const LABELLABLE = new Set<unknown>([Input, Textarea, Select, NumberInput]);

/** Same API as ui/input's Field, but the label is programmatically tied to its control (and errors set aria-invalid). */
export function Field({
  label, hint, error, children, className,
}: { label?: React.ReactNode; hint?: React.ReactNode; error?: React.ReactNode; children: React.ReactNode; className?: string }) {
  const auto = React.useId();
  const child = React.isValidElement<{ id?: string; "aria-invalid"?: boolean }>(children) && LABELLABLE.has(children.type) ? children : null;
  const id = child?.props.id ?? auto;
  return (
    <div className={className}>
      {label && <Label htmlFor={child ? id : undefined}>{label}</Label>}
      {child ? React.cloneElement(child, { id, "aria-invalid": error ? true : child.props["aria-invalid"] }) : children}
      {error ? <p className="mt-1.5 text-[13px] text-danger">{error}</p> : hint ? <p className="mt-1.5 text-[13px] text-ink-2">{hint}</p> : null}
    </div>
  );
}

export function FormCard({
  title, description, children, action, id, className,
}: { title: React.ReactNode; description?: React.ReactNode; children: React.ReactNode; action?: React.ReactNode; id?: string; className?: string }) {
  return (
    <section id={id} className={cn("scroll-mt-24 rounded-2xl border border-line-soft bg-white", className)}>
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line-soft px-5 py-4 sm:px-6">
        <div className="min-w-0">
          <h2 className="text-[17px] font-bold tracking-tight">{title}</h2>
          {description && <p className="mt-0.5 text-[13.5px] text-ink-2">{description}</p>}
        </div>
        {action}
      </header>
      <div className="space-y-5 px-5 py-5 sm:px-6">{children}</div>
    </section>
  );
}

const CALLOUT_TONES = {
  info: { box: "border-ocean-100 bg-ocean-50/70", icon: "text-ocean-600", Icon: Info },
  trust: { box: "border-ocean-100 bg-ocean-50/70", icon: "text-ocean-600", Icon: ShieldCheck },
  warning: { box: "border-warning/20 bg-warning-50", icon: "text-warning", Icon: TriangleAlert },
  danger: { box: "border-danger/20 bg-danger-50", icon: "text-danger", Icon: CircleAlert },
  neutral: { box: "border-line-soft bg-surface", icon: "text-ink-2", Icon: Info },
};

export function Callout({
  tone = "info", title, children, icon, action, className,
}: { tone?: keyof typeof CALLOUT_TONES; title?: React.ReactNode; children?: React.ReactNode; icon?: React.ReactNode; action?: React.ReactNode; className?: string }) {
  const t = CALLOUT_TONES[tone];
  return (
    <div className={cn("flex gap-3 rounded-xl border px-4 py-3.5 text-[13.5px] leading-relaxed", t.box, className)}>
      <span className={cn("mt-0.5 shrink-0", t.icon)}>{icon ?? <t.Icon className="size-[18px]" />}</span>
      <div className="min-w-0 flex-1 text-ink-2">
        {title && <p className="font-semibold text-ink">{title}</p>}
        {children && <div className={cn(title && "mt-0.5")}>{children}</div>}
      </div>
      {action && <div className="shrink-0 self-center">{action}</div>}
    </div>
  );
}

export function Segmented<T extends string | number>({
  value, onChange, options, className, size = "md", label,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: React.ReactNode; count?: number }[];
  className?: string;
  size?: "sm" | "md";
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn("no-scrollbar inline-flex max-w-full overflow-x-auto rounded-full border border-line-soft bg-white p-1", className)}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={String(o.value)}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={cn(
              "shrink-0 rounded-full px-3.5 font-semibold whitespace-nowrap transition-colors",
              size === "sm" ? "h-7 text-[12.5px]" : "h-8 text-[13px]",
              active ? "bg-ink text-white shadow-sm" : "text-ink-2 hover:bg-surface hover:text-ink",
            )}
          >
            {o.label}
            {o.count !== undefined && <span className={cn("ml-1.5 tabular-nums", active ? "text-white/70" : "text-ink-3")}>{o.count}</span>}
          </button>
        );
      })}
    </div>
  );
}

export function IconButton({
  label, children, className, tone = "default", ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string; tone?: "default" | "danger" }) {
  return (
    <Tooltip content={label}>
      <button
        type="button"
        aria-label={label}
        className={cn(
          "grid size-8 shrink-0 place-items-center rounded-full text-ink-2 transition hover:bg-surface hover:text-ink disabled:pointer-events-none disabled:opacity-30 [&_svg]:size-4",
          tone === "danger" && "hover:bg-danger-50 hover:text-danger",
          className,
        )}
        {...props}
      >
        {children}
      </button>
    </Tooltip>
  );
}

export function CopyButton({ value, label = "Copy", className, compact }: { value: string; label?: string; className?: string; compact?: boolean }) {
  const [copied, setCopied] = React.useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = value;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    setCopied(true);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopied(false), 1600);
  };
  if (compact) {
    return (
      <IconButton label={copied ? "Copied" : label} onClick={copy} className={className}>
        {copied ? <Check className="text-success" /> : <Copy />}
      </IconButton>
    );
  }
  return (
    <Button type="button" variant="soft" size="sm" onClick={copy} className={className}>
      {copied ? <Check className="size-4 text-success" /> : <Copy className="size-4" />}
      {copied ? "Copied" : label}
    </Button>
  );
}

/** Read-only value with a copy button — callback URLs, iCal links. */
export function CopyField({ value, label }: { value: string; label?: string }) {
  return (
    <div className="flex min-w-0 items-center gap-1 rounded-lg border border-line bg-surface py-1 pr-1 pl-3">
      <code className="min-w-0 flex-1 truncate font-mono text-[12.5px] text-ink" title={value}>
        {value}
      </code>
      <CopyButton value={value} label={label ?? "Copy"} compact />
    </div>
  );
}

export function SwitchRow({
  label, description, checked, onCheckedChange, disabled, className,
}: { label: React.ReactNode; description?: React.ReactNode; checked: boolean; onCheckedChange: (v: boolean) => void; disabled?: boolean; className?: string }) {
  const id = React.useId();
  return (
    <div className={cn("flex items-start justify-between gap-6", className)}>
      <div className="min-w-0">
        <label htmlFor={id} className="cursor-pointer text-[15px] font-semibold">
          {label}
        </label>
        {description && <p className="mt-0.5 text-[13px] leading-relaxed text-ink-2">{description}</p>}
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onCheckedChange} disabled={disabled} />
    </div>
  );
}

export const AffixInput = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement> & { before?: React.ReactNode; after?: React.ReactNode }
>(({ before, after, className, ...props }, ref) => (
  <div className="relative">
    {before && <span className="pointer-events-none absolute inset-y-0 left-3.5 flex items-center text-[13px] font-semibold text-ink-2">{before}</span>}
    <Input ref={ref} className={cn("tabular-nums", before && "pl-12", after && "pr-16", className)} {...props} />
    {after && <span className="pointer-events-none absolute inset-y-0 right-3.5 flex items-center text-[13px] text-ink-2">{after}</span>}
  </div>
));
AffixInput.displayName = "AffixInput";

/** Numeric input that keeps the typed text (so "1." or "" don't jump) and reports numbers or null. */
export function NumberInput({
  value, onValueChange, decimal, before, after, ...props
}: Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange"> & {
  value: number | string | null | undefined;
  onValueChange: (v: number | null) => void;
  decimal?: boolean;
  before?: React.ReactNode;
  after?: React.ReactNode;
}) {
  const asText = (v: typeof value) => (v === null || v === undefined || v === "" ? "" : String(Number(v)));
  const [text, setText] = React.useState(() => asText(value));
  const [seen, setSeen] = React.useState(value);
  if (seen !== value) {
    setSeen(value);
    const parsed = text === "" || text === "-" ? null : Number(text);
    const incoming = value === null || value === undefined || value === "" ? null : Number(value);
    if (parsed !== incoming) setText(asText(value));
  }
  const pattern = decimal ? /^-?\d*\.?\d*$/ : /^-?\d*$/;
  return (
    <AffixInput
      {...props}
      before={before}
      after={after}
      inputMode={decimal ? "decimal" : "numeric"}
      value={text}
      onChange={(e) => {
        const t = e.target.value.replace(/,/g, "");
        if (!pattern.test(t)) return;
        setText(t);
        if (t === "" || t === "-") onValueChange(null);
        else if (!t.endsWith(".")) onValueChange(Number(t));
      }}
    />
  );
}

export function CharCount({ value, max, className }: { value: string; max: number; className?: string }) {
  const n = value.length;
  return <span className={cn("text-xs tabular-nums", n > max ? "font-semibold text-danger" : n > max * 0.9 ? "text-warning" : "text-ink-3", className)}>{n}/{max}</span>;
}

export function ChoiceCards<T extends string>({
  value, onChange, options, columns = 2, label,
}: { value: T; onChange: (v: T) => void; options: { value: T; title: React.ReactNode; text?: React.ReactNode; icon?: React.ReactNode }[]; columns?: 2 | 3 | 4; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className={cn("grid gap-2.5", columns === 2 ? "sm:grid-cols-2" : columns === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2 xl:grid-cols-4")}>
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={cn(
              "relative rounded-xl border px-4 py-3 text-left transition",
              active ? "border-ink bg-white ring-1 ring-ink" : "border-line bg-white hover:border-ink-3",
            )}
          >
            <span className="flex items-center gap-2 text-[14px] font-semibold">
              {o.icon}
              {o.title}
            </span>
            {o.text && <span className="mt-1 block text-[12.5px] leading-snug text-ink-2">{o.text}</span>}
            {active && (
              <span className="absolute top-3 right-3 grid size-5 place-items-center rounded-full bg-ink text-white">
                <Check className="size-3" strokeWidth={3} />
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function StringListEditor({
  value, onChange, placeholder, addLabel = "Add", label,
}: { value: string[]; onChange: (v: string[]) => void; placeholder?: string; addLabel?: string; label: string }) {
  const [draft, setDraft] = React.useState("");
  const add = () => {
    const t = draft.trim();
    if (!t) return;
    onChange([...value, t]);
    setDraft("");
  };
  const move = (i: number, d: number) => {
    const next = [...value];
    const [item] = next.splice(i, 1);
    next.splice(i + d, 0, item);
    onChange(next);
  };
  return (
    <div className="space-y-2">
      {value.length > 0 && (
        <ol className="space-y-2">
          {value.map((item, i) => (
            <li key={i} className="flex items-center gap-1.5">
              <span className="w-5 shrink-0 text-right text-xs font-semibold text-ink-3 tabular-nums">{i + 1}</span>
              <Input value={item} aria-label={`${label} ${i + 1}`} onChange={(e) => onChange(value.map((v, j) => (j === i ? e.target.value : v)))} className="h-10" />
              <IconButton label="Move up" disabled={i === 0} onClick={() => move(i, -1)}>
                <ArrowUp />
              </IconButton>
              <IconButton label="Move down" disabled={i === value.length - 1} onClick={() => move(i, 1)}>
                <ArrowDown />
              </IconButton>
              <IconButton label="Remove" tone="danger" onClick={() => onChange(value.filter((_, j) => j !== i))}>
                <X />
              </IconButton>
            </li>
          ))}
        </ol>
      )}
      <div className="flex gap-2 pl-6.5">
        <Input
          value={draft}
          aria-label={`New ${label.toLowerCase()}`}
          placeholder={placeholder}
          className="h-10"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <Button type="button" variant="soft" className="h-10" onClick={add} disabled={!draft.trim()}>
          <Plus className="size-4" /> {addLabel}
        </Button>
      </div>
    </div>
  );
}

// ---------- save bar & dialogs ----------

// on phones it floats above the bottom tab bar (64px + safe area), not behind it
export function SaveBar({
  count, saving, onSave, onDiscard, saveLabel = "Save changes",
}: { count: number; saving?: boolean; onSave: () => void; onDiscard: () => void; saveLabel?: string }) {
  useUnsavedChanges(count > 0, onSave);
  if (!count) return null;
  return (
    <div className="pointer-events-none sticky bottom-[calc(80px+env(safe-area-inset-bottom))] z-30 mt-6 flex justify-center md:bottom-4">
      <div role="status" className="pointer-events-auto flex w-full max-w-2xl items-center gap-2 rounded-2xl bg-ink py-2.5 pr-2.5 pl-5 text-white shadow-float animate-slide-up">
        <span className="size-2 shrink-0 animate-pulse rounded-full bg-brand-400" />
        <p className="min-w-0 flex-1 truncate text-sm font-semibold">
          {plural(count, "unsaved change")}
          <span className="ml-2 hidden font-normal text-white/60 sm:inline">⌘S to save</span>
        </p>
        <Button type="button" variant="ghost" size="sm" className="text-white hover:bg-white/10" onClick={onDiscard} disabled={saving}>
          Discard
        </Button>
        <Button type="button" variant="brand" size="sm" onClick={onSave} loading={saving}>
          {saveLabel}
        </Button>
      </div>
    </div>
  );
}

export function ConfirmDialog({
  open, onOpenChange, title, children, confirmLabel = "Confirm", tone = "dark", loading, onConfirm, disabled,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  title: string;
  children?: React.ReactNode;
  confirmLabel?: string;
  tone?: "dark" | "danger" | "brand";
  loading?: boolean;
  disabled?: boolean;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        size="sm"
        title={title}
        footer={
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="ghost">Cancel</Button>
            </DialogClose>
            <Button variant={tone} loading={loading} disabled={disabled} onClick={onConfirm}>
              {confirmLabel}
            </Button>
          </div>
        }
      >
        <div className="space-y-4 px-6 py-5 text-[15px] leading-relaxed text-ink-2">{children}</div>
      </DialogContent>
    </Dialog>
  );
}

// ---------- SMS ----------

export function SmsMeter({ text, onFix, className }: { text: string; onFix?: (fixed: string) => void; className?: string }) {
  const info = smsInfo(text);
  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[12.5px] text-ink-2">
        <span className="tabular-nums">
          <b className="font-semibold text-ink">{info.length}</b> / {info.limit} characters
        </span>
        <span className="text-ink-3">·</span>
        <span className={cn("font-semibold tabular-nums", info.segments > 2 ? "text-warning" : "text-ink")}>
          {info.segments === 0 ? "0 SMS" : plural(info.segments, "SMS part")}
        </span>
        <Tooltip content={info.encoding === "GSM-7" ? "Standard SMS alphabet: 160 characters, or 153 per part when split." : "A character outside the GSM alphabet switches the whole message to Unicode: 70 characters, or 67 per part."}>
          <span>
            <Badge tone={info.encoding === "GSM-7" ? "neutral" : "warning"}>{info.encoding}</Badge>
          </span>
        </Tooltip>
      </div>
      {info.offenders.length > 0 && (
        <p className="text-[12.5px] text-warning">
          {info.offenders.slice(0, 6).map((c) => `“${describeChar(c)}”`).join(" ")} {info.offenders.length === 1 ? "isn't" : "aren't"} in the GSM alphabet, so each SMS fits only 70 characters.{" "}
          {onFix && (
            <button type="button" className="font-semibold underline underline-offset-2" onClick={() => onFix(toGsm(text))}>
              Convert to plain text
            </button>
          )}
        </p>
      )}
    </div>
  );
}

export function PhonePreview({ text, sender = "AminaStays", footer, className }: { text: React.ReactNode; sender?: string; footer?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("mx-auto w-full max-w-[330px]", className)}>
      <div className="rounded-[2.2rem] bg-ink p-2 shadow-float">
        <div className="overflow-hidden rounded-[1.8rem] bg-[#f2f2f7]">
          <div className="flex flex-col items-center gap-1 border-b border-black/5 bg-white/90 px-4 pt-5 pb-3">
            <span className="grid size-10 place-items-center rounded-full bg-gradient-to-br from-brand-400 to-brand-600 text-sm font-bold text-white">AS</span>
            <span className="text-[12px] font-semibold text-ink">{sender}</span>
          </div>
          <div className="min-h-44 px-3 py-4">
            <p className="mb-2 text-center text-[11px] font-medium text-ink-3">Text Message · SMS</p>
            <div className="max-w-[88%] rounded-[1.1rem] rounded-bl-[0.35rem] bg-white px-3.5 py-2 text-[14px] leading-snug break-words whitespace-pre-wrap text-ink shadow-sm">
              {text}
            </div>
          </div>
        </div>
      </div>
      {footer && <div className="mt-3 text-center text-[12.5px] text-ink-2">{footer}</div>}
    </div>
  );
}

// ---------- data display ----------

export function Flag({ code, withName }: { code?: string | null; withName?: boolean }) {
  if (!code) return <span className="text-ink-3">—</span>;
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap" title={countryName(code)}>
      <span aria-hidden className="text-base leading-none">{flag(code)}</span>
      <span className="text-[13px] text-ink-2">{withName ? countryName(code) : code.toUpperCase()}</span>
    </span>
  );
}

export function StatTile({ label, value, hint, className }: { label: React.ReactNode; value: React.ReactNode; hint?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-xl border border-line-soft bg-white px-4 py-3", className)}>
      <p className="text-[12px] font-semibold tracking-wide text-ink-2 uppercase">{label}</p>
      <p className="mt-1 text-xl font-bold tracking-tight tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 text-[12.5px] text-ink-2">{hint}</p>}
    </div>
  );
}

export function Pill({ children, tone = "neutral", className }: { children: React.ReactNode; tone?: "neutral" | "ink" | "brand" | "ocean"; className?: string }) {
  const tones = { neutral: "border-line-soft bg-surface text-ink-2", ink: "border-ink bg-ink text-white", brand: "border-brand-100 bg-brand-50 text-brand-700", ocean: "border-ocean-100 bg-ocean-50 text-ocean-700" };
  return <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11.5px] font-semibold whitespace-nowrap", tones[tone], className)}>{children}</span>;
}

export function TableCard({ title, description, action, children, className }: { title?: React.ReactNode; description?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("overflow-hidden rounded-2xl border border-line-soft bg-white", className)}>
      {(title || action) && (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line-soft px-5 py-4">
          <div className="min-w-0">
            {title && <h2 className="text-[15px] font-bold">{title}</h2>}
            {description && <p className="mt-0.5 text-[13px] text-ink-2">{description}</p>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}
