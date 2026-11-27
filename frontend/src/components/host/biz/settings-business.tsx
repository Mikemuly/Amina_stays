"use client";

import { useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Banknote, Building2, KeyRound, MessageSquareText, Radio } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ErrorBlock, LoadingBlock } from "@/components/host/common";
import { usePayOptions } from "@/components/providers";
import { Input, Label, Select } from "@/components/ui/input";
import { patch } from "@/lib/api";
import { cn } from "@/lib/utils";

import { useHostSettings, useInvalidateHost } from "./queries";
import type { HostSettings } from "./types";
import { Callout, Field, FormCard, HOURS, NumberInput, SaveBar, SwitchRow, errorMessage, fieldErrors } from "./ui";

type Key = Exclude<keyof HostSettings, "updated_at">;
type Kind = "text" | "email" | "tel" | "time" | "hour" | "int" | "decimal" | "switch" | "date";

interface Def {
  key: Key;
  label: string;
  kind: Kind;
  help?: React.ReactNode;
  before?: string;
  after?: string;
  placeholder?: string;
  wide?: boolean;
  mono?: boolean;
}

const sectionsFor = (mpesa: boolean): { id: string; title: string; description: string; icon: React.ComponentType<{ className?: string }>; fields: Def[] }[] => [
  {
    id: "business",
    title: "Business profile",
    description: "How Amina Stays introduces itself in every SMS, call and on the website.",
    icon: Building2,
    fields: [
      { key: "business_name", label: "Business name", kind: "text" },
      { key: "host_name", label: "Host name", kind: "text", help: "Signs replies — “Amina: Karibu!”" },
      { key: "tagline", label: "Tagline", kind: "text", wide: true },
      { key: "support_email", label: "Support email", kind: "email" },
      { key: "host_phone", label: "Host phone", kind: "tel", mono: true, help: "Gets relayed questions, SOS calls and the 07:00 digest." },
      { key: "backup_phone", label: "Backup phone", kind: "tel", mono: true, help: "Called if an SOS isn't acknowledged within 3 minutes." },
    ],
  },
  {
    id: "arrival",
    title: "Check-in & door codes",
    description: "Defaults for every home — a listing can override its own times.",
    icon: KeyRound,
    fields: [
      { key: "default_checkin_time", label: "Check-in from", kind: "time" },
      { key: "default_checkout_time", label: "Checkout by", kind: "time" },
      { key: "code_release_time", label: "Door code goes out at", kind: "time", help: "On arrival morning, once every check below passes." },
      { key: "require_id_before_code", label: "Require an ID before the door code", kind: "switch", help: "Keeps the guest register complete — the guest gets reminders until it's in." },
      { key: "sim_swap_check", label: "SIM-swap check before the door code", kind: "switch", help: "Africa's Talking Insights flags a recently swapped SIM, a common fraud signal in Kenya." },
    ],
  },
  {
    id: "payments",
    title: "Booking & payments",
    description: "How holds, deposits and balances work on every channel.",
    icon: Banknote,
    fields: [
      { key: "hold_minutes", label: "Hold dates while paying", kind: "int", after: "minutes", help: mpesa ? "Long enough to finish the M-Pesa PIN prompt." : "Long enough to finish paying by card." },
      { key: "deposit_percent", label: "Deposit", kind: "int", after: "%", help: "For “pay part now” bookings." },
      { key: "balance_due_days", label: "Balance due", kind: "int", after: "days before", help: mpesa ? "An M-Pesa prompt for the balance goes out then." : "A payment link for the balance goes out by SMS then." },
      { key: "instant_changes", label: "Instant date changes", kind: "switch", help: "Guests can move or extend into free nights and pay the difference straight away. Off: you approve every change." },
      { key: "usd_rate", label: "US dollar", kind: "decimal", before: "KES", after: "per $", help: "Display only — guests always pay in KES." },
      { key: "eur_rate", label: "Euro", kind: "decimal", before: "KES", after: "per €" },
      { key: "gbp_rate", label: "Pound", kind: "decimal", before: "KES", after: "per £" },
    ],
  },
  {
    id: "compliance",
    title: "Tax & compliance",
    description: "Tourism Act 2011, Tourism Enterprises Regulations 2025 and the Data Protection Act 2019.",
    icon: BadgeCheck,
    fields: [
      { key: "tra_licence_number", label: "TRA licence number", kind: "text", mono: true, help: "Shown on every listing and booking page (r.19)." },
      { key: "tra_licence_expiry", label: "Licence expiry", kind: "date", help: "We warn you 45 days before it lapses." },
      { key: "odpc_registration", label: "ODPC registration", kind: "text", mono: true, help: "Data controller number from the Data Commissioner." },
      { key: "kra_pin", label: "KRA PIN", kind: "text", mono: true, placeholder: "P051234567X" },
      { key: "tourism_levy_percent", label: "Tourism levy", kind: "decimal", after: "%", help: "Added to every quote and reported monthly." },
      { key: "id_retention_days", label: "Keep guest IDs for", kind: "int", after: "days", help: "r.26 requires 5 years (1,825 days); ID numbers are erased afterwards." },
      { key: "vat_registered", label: "VAT registered", kind: "switch", help: "Required once taxable supplies pass KES 5m in 12 months — VAT is then added to quotes." },
      { key: "vat_percent", label: "VAT rate", kind: "decimal", after: "%" },
    ],
  },
  {
    id: "messaging",
    title: "Guest messaging",
    description: "When automated SMS may go out, and what Ask Amina handles alone.",
    icon: MessageSquareText,
    fields: [
      { key: "auto_answer", label: "Answer common questions automatically", kind: "switch", help: "Ask Amina replies from the knowledge base; anything else is relayed to you." },
      { key: "quiet_hours_start", label: "Quiet hours from", kind: "hour", help: "No automated SMS overnight." },
      { key: "quiet_hours_end", label: "Quiet hours until", kind: "hour" },
      { key: "promo_window_start", label: "Promotions from", kind: "hour", help: "Kenyan operators restrict promotional SMS hours." },
      { key: "promo_window_end", label: "Promotions until", kind: "hour" },
      { key: "review_delay_minutes", label: "Ask for a review", kind: "int", after: "min after checkout" },
    ],
  },
  {
    id: "extras",
    title: "Africa's Talking extras",
    description: "Small touches that use Airtime, Mobile Data and Voice.",
    icon: Radio,
    fields: [
      { key: "welcome_data_mb", label: "Welcome data bundle", kind: "int", after: "MB", help: "Gifted to Kenyan numbers on check-in. 0 = off." },
      { key: "goodwill_airtime_kes", label: "Goodwill airtime", kind: "int", before: "KES", help: "Sent automatically if you cancel a paid stay. 0 = off." },
      { key: "voice_welcome_call", label: "Welcome call on arrival day", kind: "switch", help: "A short spoken walkthrough for Kenyan guests (needs a live voice number)." },
    ],
  },
];

type Form = Omit<HostSettings, "updated_at">;

const DECIMALS: Key[] = ["tourism_levy_percent", "vat_percent", "usd_rate", "eur_rate", "gbp_rate"];

function toForm(s: HostSettings): Form {
  return Object.fromEntries(Object.entries(s).filter(([k]) => k !== "updated_at")) as Form;
}

/** Normalised value for diffing and sending (decimals as numbers, blank dates as null). */
function norm(key: Key, v: unknown) {
  if (DECIMALS.includes(key)) return v === null || v === "" ? null : Number(v);
  if (key === "tra_licence_expiry") return v || null;
  return v;
}

export function BusinessTab() {
  const { data, isLoading, error, refetch } = useHostSettings();
  if (error) return <ErrorBlock error={error} retry={refetch} />;
  if (isLoading || !data) return <LoadingBlock rows={6} />;
  return <BusinessForm settings={data} />;
}

function BusinessForm({ settings }: { settings: HostSettings }) {
  const qc = useQueryClient();
  const invalidate = useInvalidateHost();
  const sections = sectionsFor(usePayOptions().mpesa);
  const base = React.useMemo(() => toForm(settings), [settings]);
  const [draft, setDraft] = React.useState<Form>(base);
  const [seen, setSeen] = React.useState(base);
  const keys = Object.keys(base) as Key[];
  const changed = keys.filter((k) => JSON.stringify(norm(k, base[k])) !== JSON.stringify(norm(k, draft[k])));
  if (seen !== base) {
    setSeen(base);
    if (keys.every((k) => JSON.stringify(norm(k, seen[k])) === JSON.stringify(norm(k, draft[k])))) setDraft(base);
  }
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    const id = window.location.hash.slice(1);
    if (id) document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  const set = (key: Key, value: unknown) => {
    setDraft((d) => ({ ...d, [key]: value }));
    if (errors[key]) setErrors((e) => Object.fromEntries(Object.entries(e).filter(([k]) => k !== key)));
  };

  const save = async () => {
    setSaving(true);
    try {
      const body = Object.fromEntries(changed.map((k) => [k, norm(k, draft[k])]));
      const updated = await patch<HostSettings>("/api/host/settings", body);
      qc.setQueryData(["host", "settings"], updated);
      setDraft(toForm(updated));
      setErrors({});
      invalidate();
      toast.success("Settings saved", { description: "Applied to the website, USSD, SMS and voice straight away." });
    } catch (e) {
      const fe = fieldErrors(e);
      setErrors(fe);
      const first = Object.keys(fe)[0];
      if (first) document.getElementById(`field-${first}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      toast.error(errorMessage(e, "Couldn't save settings."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[200px_minmax(0,1fr)]">
      <nav aria-label="Settings sections" className="hidden lg:sticky lg:top-6 lg:block lg:self-start">
        <ul className="space-y-1">
          {sections.map((s) => {
            const dirty = s.fields.some((f) => changed.includes(f.key));
            return (
              <li key={s.id}>
                <a href={`#${s.id}`} className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-[14px] font-medium text-ink-2 transition-colors hover:bg-white hover:text-ink">
                  <s.icon className="size-4 shrink-0" />
                  <span className="flex-1">{s.title}</span>
                  {dirty && <span className="size-2 rounded-full bg-brand-500" aria-label="unsaved changes" />}
                </a>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="min-w-0 space-y-6">
        {sections.map((s) => (
          <FormCard key={s.id} id={s.id} title={s.title} description={s.description}>
            {s.id === "compliance" && (
              <Callout tone="trust">
                These details appear on listings, booking confirmations and the TRA return. The compliance checklist under Safety shows anything missing.
              </Callout>
            )}
            <div className="grid gap-x-5 gap-y-5 sm:grid-cols-2 xl:grid-cols-3">
              {s.fields.map((f) => (
                <SettingField key={f.key} def={f} value={draft[f.key]} error={errors[f.key]} onChange={(v) => set(f.key, v)} disabled={f.key === "vat_percent" && !draft.vat_registered} />
              ))}
            </div>
          </FormCard>
        ))}
        <SaveBar
          count={changed.length}
          saving={saving}
          onSave={save}
          onDiscard={() => {
            setDraft(base);
            setErrors({});
          }}
        />
      </div>
    </div>
  );
}

function SettingField({ def: f, value, error, onChange, disabled }: { def: Def; value: unknown; error?: string; onChange: (v: unknown) => void; disabled?: boolean }) {
  const id = `field-${f.key}`;
  if (f.kind === "switch") {
    return (
      <div id={id} className={cn("rounded-xl border border-line-soft p-4 sm:col-span-2 xl:col-span-3", error && "border-danger/40")}>
        <SwitchRow label={f.label} description={f.help} checked={!!value} onCheckedChange={onChange} />
        {error && <p className="mt-1.5 text-[13px] text-danger">{error}</p>}
      </div>
    );
  }
  let control: React.ReactNode;
  if (f.kind === "hour") {
    control = (
      <Select id={id} value={String(value ?? 0)} onChange={(e) => onChange(Number(e.target.value))}>
        {HOURS.map((h) => (
          <option key={h.value} value={h.value}>
            {h.label}
          </option>
        ))}
      </Select>
    );
  } else if (f.kind === "int" || f.kind === "decimal") {
    control = (
      <NumberInput
        id={id}
        decimal={f.kind === "decimal"}
        value={value as number | string | null}
        onValueChange={onChange}
        before={f.before}
        after={f.after}
        disabled={disabled}
        className={cn(f.after && (f.after.length <= 2 ? "pr-9" : f.after.length <= 7 ? "pr-20" : f.after.length <= 12 ? "pr-28" : "pr-40"))}
      />
    );
  } else {
    control = (
      <Input
        id={id}
        type={f.kind === "text" ? "text" : f.kind}
        value={(value as string | null) ?? ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={f.placeholder}
        className={cn(f.mono && "font-mono")}
      />
    );
  }
  return (
    <Field hint={f.help} error={error} className={cn(f.wide && "sm:col-span-2")}>
      <Label htmlFor={id}>{f.label}</Label>
      {control}
    </Field>
  );
}
