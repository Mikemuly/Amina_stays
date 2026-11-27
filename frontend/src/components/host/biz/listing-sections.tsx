"use client";

import { Check, Eye, EyeOff, ExternalLink, MapPin, Plus, Search, X } from "lucide-react";
import * as React from "react";

import { useConfig } from "@/components/providers";
import { Icon } from "@/components/icon";
import { Button } from "@/components/ui/button";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Skeleton, Stepper } from "@/components/ui/misc";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/overlays";
import { hhmm, kes } from "@/lib/format";
import { cn } from "@/lib/utils";

import {
  ACCESS_METHODS, BATHROOM_OPTIONS, HIGHLIGHT_ICONS, LISTING_TAGS, POLICY_TEXT, PROPERTY_TYPES, type SectionProps,
} from "./listing-form";
import { STATUS_META } from "./listings";
import { useAmenities, useAreas, useHostSettings } from "./queries";
import type { CancellationPolicy, Highlight, ListingStatus, Sleeping } from "./types";
import { Callout, CharCount, ChoiceCards, Field, FormCard, IconButton, NumberInput, StringListEditor, SwitchRow, humanize } from "./ui";

// ---------- Details ----------

export function DetailsSection({ draft, set, errors }: SectionProps) {
  const { data: areas } = useAreas();
  return (
    <>
      <FormCard title="The basics" description="What guests see first on cards, in search and in SMS replies.">
        <Field label={<LabelRow label="Listing name" right={<CharCount value={draft.name} max={80} />} />} error={errors.name}>
          <Input value={draft.name} maxLength={90} placeholder="e.g. Nyali Breeze Studio" onChange={(e) => set("name", e.target.value)} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Area" error={errors.area} hint="Guests search and browse by area on every channel.">
            <Select value={draft.area} onChange={(e) => set("area", e.target.value)}>
              {(areas ?? []).map((a) => (
                <option key={a.slug} value={a.slug}>
                  {a.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Property type" error={errors.property_type}>
            <Select value={draft.property_type} onChange={(e) => set("property_type", e.target.value)}>
              {PROPERTY_TYPES.map((t) => (
                <option key={t} value={t}>
                  {humanize(t)}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field
          label={<LabelRow label="Summary" right={<CharCount value={draft.summary} max={240} />} />}
          error={errors.summary}
          hint="One-line pitch on listing cards — and the line USSD and SMS guests hear about this home."
        >
          <Textarea value={draft.summary} rows={2} className="min-h-0" placeholder="Bright studio steps from Nyali's cafés…" onChange={(e) => set("summary", e.target.value)} />
        </Field>
        <Field label="Description" error={errors.description}>
          <Textarea value={draft.description} rows={6} onChange={(e) => set("description", e.target.value)} />
        </Field>
        <div className="grid gap-4 lg:grid-cols-3">
          <Field label="The space" error={errors.the_space}>
            <Textarea value={draft.the_space} rows={4} onChange={(e) => set("the_space", e.target.value)} />
          </Field>
          <Field label="Guest access" error={errors.guest_access}>
            <Textarea value={draft.guest_access} rows={4} onChange={(e) => set("guest_access", e.target.value)} />
          </Field>
          <Field label="The neighbourhood" error={errors.neighbourhood}>
            <Textarea value={draft.neighbourhood} rows={4} onChange={(e) => set("neighbourhood", e.target.value)} />
          </Field>
        </div>
      </FormCard>

      <FormCard title="Rooms & capacity" description="Used to filter search results by guests and bedrooms.">
        <div className="grid gap-x-8 gap-y-1 sm:grid-cols-2">
          <CountRow label="Bedrooms" value={draft.bedrooms} min={0} onChange={(v) => set("bedrooms", v)} error={errors.bedrooms} />
          <CountRow label="Beds" value={draft.beds} min={1} onChange={(v) => set("beds", v)} error={errors.beds} />
          <CountRow label="Maximum guests" value={draft.max_guests} min={1} max={20} onChange={(v) => set("max_guests", v)} error={errors.max_guests} />
          <div className="flex items-center justify-between gap-4 border-b border-line-soft py-3.5">
            <label htmlFor="bathrooms" className="text-[15px] font-medium">
              Bathrooms
            </label>
            <Select id="bathrooms" value={draft.bathrooms} onChange={(e) => set("bathrooms", e.target.value)} className="h-9 w-24 text-sm">
              {(BATHROOM_OPTIONS.includes(draft.bathrooms) ? BATHROOM_OPTIONS : [draft.bathrooms, ...BATHROOM_OPTIONS]).map((b) => (
                <option key={b} value={b}>
                  {b}
                </option>
              ))}
            </Select>
          </div>
        </div>
        <Field label="Size" error={errors.size_sqm} className="max-w-48">
          <NumberInput value={draft.size_sqm} onValueChange={(v) => set("size_sqm", v)} after="m²" placeholder="Optional" />
        </Field>
        <div>
          <p className="mb-1.5 text-[13px] font-semibold">Sleeping arrangements</p>
          <SleepingEditor value={draft.sleeping} onChange={(v) => set("sleeping", v)} />
          {errors.sleeping && <p className="mt-1.5 text-[13px] text-danger">{errors.sleeping}</p>}
        </div>
      </FormCard>

      <FormCard title="Highlights" description="Three short reasons to book, shown near the top of the listing page.">
        <HighlightsEditor value={draft.highlights} onChange={(v) => set("highlights", v)} />
        {errors.highlights && <p className="text-[13px] text-danger">{errors.highlights}</p>}
        <div>
          <p className="mb-2 text-[13px] font-semibold">Categories</p>
          <div className="flex flex-wrap gap-2">
            {LISTING_TAGS.map((t) => {
              const on = draft.tags.includes(t);
              return (
                <button
                  key={t}
                  type="button"
                  aria-pressed={on}
                  onClick={() => set("tags", on ? draft.tags.filter((x) => x !== t) : [...draft.tags, t])}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-[13px] font-semibold transition",
                    on ? "border-ink bg-ink text-white" : "border-line bg-white text-ink-2 hover:border-ink-3 hover:text-ink",
                  )}
                >
                  {on && <Check className="size-3.5" strokeWidth={3} />}
                  {humanize(t.replace(/-/g, " "))}
                </button>
              );
            })}
          </div>
          <p className="mt-2 text-[13px] text-ink-2">Categories power the filter chips on the guest website (Beachfront, Pool, Family…).</p>
        </div>
      </FormCard>

      <FormCard title="Visibility">
        <ChoiceCards<ListingStatus>
          label="Listing status"
          columns={3}
          value={draft.status}
          onChange={(v) => set("status", v)}
          options={(Object.keys(STATUS_META) as ListingStatus[]).map((s) => ({
            value: s,
            title: STATUS_META[s].label,
            text: STATUS_META[s].text,
            icon: <span className={cn("size-2 rounded-full", STATUS_META[s].dot)} />,
          }))}
        />
        {errors.status && <p className="text-[13px] text-danger">{errors.status}</p>}
        <SwitchRow
          label="Featured home"
          description="Shown first on the homepage and offered first when USSD and SMS guests ask for options."
          checked={draft.is_featured}
          onCheckedChange={(v) => set("is_featured", v)}
        />
      </FormCard>
    </>
  );
}

function LabelRow({ label, right }: { label: string; right: React.ReactNode }) {
  return (
    <span className="flex items-center justify-between gap-3">
      {label}
      {right}
    </span>
  );
}

function CountRow({ label, value, onChange, min, max = 16, error }: { label: string; value: number; onChange: (v: number) => void; min: number; max?: number; error?: string }) {
  return (
    <div className="border-b border-line-soft py-3.5">
      <div className="flex items-center justify-between gap-4">
        <span className="text-[15px] font-medium">{label}</span>
        <Stepper value={value} min={min} max={max} onChange={onChange} label={label.toLowerCase()} />
      </div>
      {error && <p className="mt-1 text-[13px] text-danger">{error}</p>}
    </div>
  );
}

function SleepingEditor({ value, onChange }: { value: Sleeping[]; onChange: (v: Sleeping[]) => void }) {
  const update = (i: number, patch: Partial<Sleeping>) => onChange(value.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  return (
    <div className="space-y-2">
      {value.map((s, i) => (
        <div key={i} className="flex items-center gap-2">
          <Input value={s.room} aria-label={`Room ${i + 1}`} placeholder="Bedroom 1" className="h-10 sm:max-w-56" onChange={(e) => update(i, { room: e.target.value })} />
          <Input value={s.beds} aria-label={`Beds in room ${i + 1}`} placeholder="1 queen bed" className="h-10" onChange={(e) => update(i, { beds: e.target.value })} />
          <IconButton label="Remove room" tone="danger" onClick={() => onChange(value.filter((_, j) => j !== i))}>
            <X />
          </IconButton>
        </div>
      ))}
      <Button type="button" variant="soft" size="sm" onClick={() => onChange([...value, { room: `Bedroom ${value.length + 1}`, beds: "" }])}>
        <Plus className="size-4" /> Add room
      </Button>
    </div>
  );
}

function HighlightsEditor({ value, onChange }: { value: Highlight[]; onChange: (v: Highlight[]) => void }) {
  const update = (i: number, patch: Partial<Highlight>) => onChange(value.map((h, j) => (j === i ? { ...h, ...patch } : h)));
  return (
    <div className="space-y-3">
      {value.map((h, i) => (
        <div key={i} className="flex gap-3 rounded-xl border border-line-soft p-3">
          <IconPicker value={h.icon} onChange={(icon) => update(i, { icon })} />
          <div className="min-w-0 flex-1 space-y-2">
            <Input value={h.title} aria-label={`Highlight ${i + 1} title`} placeholder="Self check-in" className="h-10 font-semibold" onChange={(e) => update(i, { title: e.target.value })} />
            <Input value={h.text} aria-label={`Highlight ${i + 1} text`} placeholder="Your door code arrives by SMS on the morning you arrive." className="h-10" onChange={(e) => update(i, { text: e.target.value })} />
          </div>
          <IconButton label="Remove highlight" tone="danger" onClick={() => onChange(value.filter((_, j) => j !== i))}>
            <X />
          </IconButton>
        </div>
      ))}
      {value.length < 6 && (
        <Button type="button" variant="soft" size="sm" onClick={() => onChange([...value, { icon: "sparkles", title: "", text: "" }])}>
          <Plus className="size-4" /> Add highlight
        </Button>
      )}
    </div>
  );
}

export function IconPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [open, setOpen] = React.useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Icon: ${value}. Change icon`}
          className="grid size-[88px] shrink-0 place-items-center rounded-xl border border-line bg-surface text-ink transition hover:border-ink"
        >
          <Icon name={value} className="size-7" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-3">
        <p className="mb-2 px-1 text-xs font-semibold text-ink-2">Choose an icon</p>
        <div className="grid grid-cols-7 gap-1">
          {HIGHLIGHT_ICONS.map((name) => (
            <button
              key={name}
              type="button"
              aria-label={name}
              title={name}
              onClick={() => {
                onChange(name);
                setOpen(false);
              }}
              className={cn("grid size-9 place-items-center rounded-lg transition hover:bg-surface", name === value && "bg-ink text-white hover:bg-ink")}
            >
              <Icon name={name} className="size-[18px]" />
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

// ---------- Pricing ----------

const POLICIES: CancellationPolicy[] = ["flexible", "moderate", "firm", "strict"];

export function PricingSection({ draft, set, errors }: SectionProps) {
  const { data: config } = useConfig();
  const base = draft.base_price ?? 0;
  const weekend = draft.weekend_price ?? base;
  const weekAvg = ((5 * base + 2 * weekend) / 7) * (1 - (draft.weekly_discount ?? 0) / 100);
  const monthAvg = ((20 * base + 8 * weekend) / 28) * (1 - (draft.monthly_discount ?? 0) / 100);
  return (
    <>
      <FormCard title="Nightly price" description="Season, weekday and last-minute rules (Settings → Pricing rules) and calendar overrides apply on top.">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div className="grid content-start gap-4 sm:grid-cols-2">
            <Field label="Base price" error={errors.base_price} hint="Per night, Sunday–Thursday.">
              <NumberInput before="KES" value={draft.base_price} onValueChange={(v) => set("base_price", v)} placeholder="4,500" />
            </Field>
            <Field label="Weekend price" error={errors.weekend_price} hint="Friday & Saturday nights. Blank = base price.">
              <NumberInput before="KES" value={draft.weekend_price} onValueChange={(v) => set("weekend_price", v)} placeholder="Same as base" />
            </Field>
            <Field label="Cleaning fee" error={errors.cleaning_fee} hint="Once per stay.">
              <NumberInput before="KES" value={draft.cleaning_fee} onValueChange={(v) => set("cleaning_fee", v)} />
            </Field>
            <div className="hidden sm:block" />
            <Field label="Weekly discount" error={errors.weekly_discount} hint="Stays of 7+ nights.">
              <NumberInput after="% off" value={draft.weekly_discount} onValueChange={(v) => set("weekly_discount", v)} />
            </Field>
            <Field label="Monthly discount" error={errors.monthly_discount} hint="Stays of 28+ nights.">
              <NumberInput after="% off" value={draft.monthly_discount} onValueChange={(v) => set("monthly_discount", v)} />
            </Field>
          </div>
          <div className="self-start rounded-xl bg-surface p-4">
            <p className="text-[12px] font-semibold tracking-wide text-ink-2 uppercase">Guests pay (before levy)</p>
            <dl className="mt-3 space-y-2.5 text-sm">
              <PreviewRow label="Weeknight" value={kes(base)} />
              <PreviewRow label="Fri / Sat night" value={kes(weekend)} />
              <PreviewRow label="7-night stay, avg / night" value={kes(weekAvg)} />
              <PreviewRow label="28-night stay, avg / night" value={kes(monthAvg)} />
            </dl>
            <p className="mt-3 border-t border-line pt-3 text-[12px] leading-relaxed text-ink-2">
              Plus {kes(draft.cleaning_fee)} cleaning and the {config?.levy_percent ?? 2}% tourism levy, shown in every quote — web, USSD and SMS.
            </p>
          </div>
        </div>
      </FormCard>

      <FormCard title="Length of stay & times">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Minimum nights" error={errors.min_nights}>
            <NumberInput after="nights" value={draft.min_nights} onValueChange={(v) => set("min_nights", v)} />
          </Field>
          <Field label="Maximum nights" error={errors.max_nights}>
            <NumberInput after="nights" value={draft.max_nights} onValueChange={(v) => set("max_nights", v)} />
          </Field>
          <Field label="Check-in from" error={errors.checkin_time} hint={`Blank = default (${hhmm(config?.business.checkin_time) || "2pm"})`}>
            <TimeInput label="Check-in from" value={draft.checkin_time} onChange={(v) => set("checkin_time", v)} />
          </Field>
          <Field label="Checkout by" error={errors.checkout_time} hint={`Blank = default (${hhmm(config?.business.checkout_time) || "11am"})`}>
            <TimeInput label="Checkout by" value={draft.checkout_time} onChange={(v) => set("checkout_time", v)} />
          </Field>
        </div>
      </FormCard>

      <FormCard title="Cancellation policy" description="Shown before guests pay and applied automatically when they cancel by web or SMS.">
        <ChoiceCards<CancellationPolicy>
          label="Cancellation policy"
          value={draft.cancellation_policy}
          onChange={(v) => set("cancellation_policy", v)}
          options={POLICIES.map((p) => ({ value: p, title: humanize(p), text: POLICY_TEXT[p] }))}
        />
        {errors.cancellation_policy && <p className="text-[13px] text-danger">{errors.cancellation_policy}</p>}
      </FormCard>
    </>
  );
}

function PreviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-ink-2">{label}</dt>
      <dd className="font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function TimeInput({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <div className="relative">
      <Input type="time" value={value} onChange={(e) => onChange(e.target.value)} aria-label={label} className={cn(value && "pr-10")} />
      {value && (
        <button type="button" aria-label="Use default time" onClick={() => onChange("")} className="absolute inset-y-0 right-2 my-auto grid size-7 place-items-center rounded-full text-ink-2 hover:bg-surface">
          <X className="size-3.5" />
        </button>
      )}
    </div>
  );
}

// ---------- Amenities ----------

const AMENITY_CATEGORIES: Record<string, string> = {
  essentials: "Essentials", coastal: "Coastal living", bedroom: "Bedroom & laundry", bathroom: "Bathroom", kitchen: "Kitchen & dining",
  entertainment: "Entertainment", family: "Family", workspace: "Workspace", outdoor: "Outdoor", parking: "Parking", safety: "Safety",
  accessibility: "Accessibility", services: "Services",
};

export function AmenitiesSection({ draft, set }: SectionProps) {
  const { data, isLoading } = useAmenities();
  const [q, setQ] = React.useState("");
  const selected = new Set(draft.amenity_codes);
  const toggle = (code: string) => set("amenity_codes", selected.has(code) ? draft.amenity_codes.filter((c) => c !== code) : [...draft.amenity_codes, code]);
  const shown = (data ?? []).filter((a) => !q || a.name.toLowerCase().includes(q.toLowerCase()));
  const groups = Object.keys(AMENITY_CATEGORIES)
    .map((cat) => ({ cat, items: shown.filter((a) => a.category === cat) }))
    .concat([{ cat: "other", items: shown.filter((a) => !(a.category in AMENITY_CATEGORIES)) }])
    .filter((g) => g.items.length);

  return (
    <FormCard
      title="Amenities"
      description={`${draft.amenity_codes.length} selected · guests can filter search by these.`}
      action={
        <div className="relative w-full sm:w-60">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find an amenity" aria-label="Find an amenity" className="h-9 pl-9 text-sm" />
        </div>
      }
    >
      {isLoading ? (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 9 }).map((_, i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      ) : (
        groups.map((g) => {
          const on = g.items.filter((a) => selected.has(a.code)).length;
          return (
            <div key={g.cat}>
              <div className="mb-2 flex items-baseline justify-between">
                <h3 className="text-[14px] font-bold">{AMENITY_CATEGORIES[g.cat] ?? "Other"}</h3>
                <span className="text-[12px] text-ink-2 tabular-nums">
                  {on} of {g.items.length}
                </span>
              </div>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {g.items.map((a) => {
                  const active = selected.has(a.code);
                  return (
                    <button
                      key={a.code}
                      type="button"
                      aria-pressed={active}
                      onClick={() => toggle(a.code)}
                      className={cn(
                        "flex items-center gap-3 rounded-xl border px-3.5 py-3 text-left text-[14px] transition",
                        active ? "border-ink bg-white font-semibold ring-1 ring-ink" : "border-line-soft text-ink-2 hover:border-ink-3 hover:text-ink",
                      )}
                    >
                      <Icon name={a.icon} className="size-5 shrink-0" />
                      <span className="min-w-0 flex-1 truncate">{a.name}</span>
                      <span className={cn("grid size-5 shrink-0 place-items-center rounded-md border", active ? "border-ink bg-ink text-white" : "border-line")}>
                        {active && <Check className="size-3.5" strokeWidth={3} />}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })
      )}
    </FormCard>
  );
}

// ---------- Rules & safety ----------

export function RulesSection({ draft, set, errors }: SectionProps) {
  return (
    <>
      <FormCard title="House rules" description="Shown before booking and repeated in the check-in SMS.">
        <StringListEditor label="House rule" value={draft.house_rules} onChange={(v) => set("house_rules", v)} placeholder="e.g. No visitors after 10pm" addLabel="Add rule" />
        <div className="divide-y divide-line-soft rounded-xl border border-line-soft px-4">
          <SwitchRow className="py-3.5" label="Pets allowed" checked={draft.pets_allowed} onCheckedChange={(v) => set("pets_allowed", v)} />
          <SwitchRow className="py-3.5" label="Smoking allowed" description="Indoors. Balconies and gardens can be covered in a house rule." checked={draft.smoking_allowed} onCheckedChange={(v) => set("smoking_allowed", v)} />
          <SwitchRow className="py-3.5" label="Events & parties allowed" checked={draft.events_allowed} onCheckedChange={(v) => set("events_allowed", v)} />
        </div>
        <Field label="Quiet hours" error={errors.quiet_hours} className="max-w-xs">
          <Input value={draft.quiet_hours} onChange={(e) => set("quiet_hours", e.target.value)} placeholder="22:00–07:00" />
        </Field>
      </FormCard>

      <FormCard title="Safety & property" description="Disclose every safety device and any camera — guests must know before they book.">
        <StringListEditor label="Safety feature" value={draft.safety_features} onChange={(v) => set("safety_features", v)} placeholder="e.g. Backup generator for power cuts" addLabel="Add" />
        <Callout tone="trust">
          Cameras must be disclosed and may only cover gates, parking or entrances — never inside the home (Airbnb policy and the Data Protection Act 2019).
        </Callout>
      </FormCard>

      <FormCard title="Breakfast">
        <SwitchRow
          label="Breakfast available"
          description="Guests can add breakfast when booking or by replying BREAKFAST by SMS — it lands on the kitchen sheet for the cook."
          checked={draft.breakfast_available}
          onCheckedChange={(v) => set("breakfast_available", v)}
        />
      </FormCard>
    </>
  );
}

// ---------- Access & arrival ----------

export function AccessSection({ draft, set, errors }: SectionProps) {
  const { data: settings } = useHostSettings();
  const [showPw, setShowPw] = React.useState(false);
  const smartLock = ["igloohome", "ttlock", "nuki"].includes(draft.access_method);
  const hasCoords = draft.latitude !== null && draft.longitude !== null;
  return (
    <>
      <Callout tone="trust" title="Private until a booking is confirmed">
        Exact address, directions and Wi-Fi go out by SMS the day before arrival (16:00). The door code follows on arrival morning — only once the
        balance is paid, the guest-register ID is in and the SIM-swap check passes.
      </Callout>

      <FormCard title="Check-in method">
        <ChoiceCards label="Check-in method" value={draft.access_method} onChange={(v) => set("access_method", v)} options={ACCESS_METHODS} columns={3} />
        {errors.access_method && <p className="text-[13px] text-danger">{errors.access_method}</p>}
        {(smartLock || draft.lock_device_id) && (
          <Field label="Lock device ID" error={errors.lock_device_id} hint="From the lock maker's app — codes are created for each stay's exact dates." className="max-w-md">
            <Input value={draft.lock_device_id} onChange={(e) => set("lock_device_id", e.target.value)} className="font-mono" />
          </Field>
        )}
      </FormCard>

      <FormCard title="Wi-Fi">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Network name" error={errors.wifi_name}>
            <Input value={draft.wifi_name} onChange={(e) => set("wifi_name", e.target.value)} autoComplete="off" />
          </Field>
          <Field label="Password" error={errors.wifi_password}>
            <div className="relative">
              <Input
                type={showPw ? "text" : "password"}
                value={draft.wifi_password}
                onChange={(e) => set("wifi_password", e.target.value)}
                autoComplete="new-password"
                aria-label="Wi-Fi password"
                className="pr-11 font-mono"
              />
              <button
                type="button"
                aria-label={showPw ? "Hide password" : "Show password"}
                onClick={() => setShowPw((s) => !s)}
                className="absolute inset-y-0 right-2 my-auto grid size-8 place-items-center rounded-full text-ink-2 hover:bg-surface"
              >
                {showPw ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          </Field>
        </div>
      </FormCard>

      <FormCard title="Finding the home">
        <Field label="Address" error={errors.address}>
          <Input value={draft.address} onChange={(e) => set("address", e.target.value)} placeholder="Apt 3, Palm Court, off Links Road, Nyali" />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Landmark" error={errors.landmark} hint="What a boda or taxi driver will recognise.">
            <Input value={draft.landmark} onChange={(e) => set("landmark", e.target.value)} placeholder="Behind City Mall, blue gate" />
          </Field>
          <Field label="Parking" error={errors.parking}>
            <Input value={draft.parking} onChange={(e) => set("parking", e.target.value)} placeholder="Free secure parking inside the compound" />
          </Field>
        </div>
        <Field label="Directions" error={errors.directions}>
          <Textarea value={draft.directions} rows={3} onChange={(e) => set("directions", e.target.value)} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)]">
          <Field label="Map link" error={errors.map_link}>
            <div className="relative">
              <Input value={draft.map_link} onChange={(e) => set("map_link", e.target.value)} placeholder="https://maps.google.com/?q=…" aria-label="Map link" className={cn(draft.map_link && "pr-11")} />
              {draft.map_link && (
                <a href={draft.map_link} target="_blank" rel="noreferrer" aria-label="Open map link" className="absolute inset-y-0 right-2 my-auto grid size-8 place-items-center rounded-full text-ink-2 hover:bg-surface">
                  <ExternalLink className="size-4" />
                </a>
              )}
            </div>
          </Field>
          <Field label="Latitude" error={errors.latitude}>
            <NumberInput decimal value={draft.latitude} onValueChange={(v) => set("latitude", v)} placeholder="-4.030000" />
          </Field>
          <Field label="Longitude" error={errors.longitude}>
            <NumberInput decimal value={draft.longitude} onValueChange={(v) => set("longitude", v)} placeholder="39.719000" />
          </Field>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-[13px] text-ink-2">
          <MapPin className="size-4" />
          The public map shows an approximate pin (300–600 m away); the exact point is shared after booking.
          {hasCoords && (
            <a className="font-semibold text-ink underline underline-offset-2" target="_blank" rel="noreferrer" href={`https://maps.google.com/?q=${draft.latitude},${draft.longitude}`}>
              Check on Google Maps
            </a>
          )}
        </div>
      </FormCard>

      <FormCard title="During the stay">
        <Field label="House manual" error={errors.house_manual} hint="AC, hot water, generator, trash — shown to booked guests on their trip page.">
          <Textarea value={draft.house_manual} rows={5} onChange={(e) => set("house_manual", e.target.value)} />
        </Field>
        <Field label="Local tips" error={errors.local_tips} hint="Sent on arrival day. Blank = the area's tips.">
          <Textarea value={draft.local_tips} rows={3} onChange={(e) => set("local_tips", e.target.value)} />
        </Field>
      </FormCard>

      <FormCard title="Licensing">
        <Field
          label="TRA licence number"
          error={errors.tra_licence_number}
          hint={`Shown on the listing and booking pages (Tourism Act). Blank = the business licence${settings?.tra_licence_number ? ` (${settings.tra_licence_number})` : ""}.`}
          className="max-w-md"
        >
          <Input value={draft.tra_licence_number} onChange={(e) => set("tra_licence_number", e.target.value)} className="font-mono" />
        </Field>
      </FormCard>
    </>
  );
}

