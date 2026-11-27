"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Icon } from "@/components/icon";
import { ErrorBlock, LoadingBlock } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Badge, EmptyState } from "@/components/ui/misc";
import { Switch } from "@/components/ui/overlays";
import { ApiError, del, get, patch, post } from "@/lib/api";
import { kes, plural } from "@/lib/format";
import { cn } from "@/lib/utils";

import { IconPicker } from "./listing-sections";
import { useInvalidateHost, useListings } from "./queries";
import type { HostAddon } from "./types";
import { ConfirmDialog, Field, IconButton, NumberInput, SwitchRow, errorMessage, fieldErrors, humanize } from "./ui";

const CATEGORIES = ["breakfast", "transport", "flexibility", "cleaning", "experience", "comfort"];
const PRICING: Record<string, string> = {
  per_stay: "per stay",
  per_night: "per night",
  per_guest_night: "per guest per night",
  per_guest: "per guest",
  per_item: "per item",
};

export function AddonsTab() {
  const invalidate = useInvalidateHost();
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["host", "addons"], queryFn: () => get<HostAddon[]>("/api/host/addons") });
  const { data: listings } = useListings();
  const [editing, setEditing] = React.useState<HostAddon | "new" | null>(null);
  const [removing, setRemoving] = React.useState<HostAddon | null>(null);

  const toggle = useMutation({
    mutationFn: (a: HostAddon) => patch<HostAddon>(`/api/host/addons/${a.id}`, { active: !a.active }),
    onSuccess: (a) => {
      toast.success(a.active ? `${a.name} is on offer again` : `${a.name} hidden from guests`);
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (a: HostAddon) => del(`/api/host/addons/${a.id}`),
    onSuccess: () => {
      toast.success("Add-on deleted");
      setRemoving(null);
      invalidate();
    },
    onError: (e) =>
      toast.error(e instanceof ApiError && e.status >= 500 ? "Guests have already booked this add-on, so it can't be deleted — switch it off instead." : errorMessage(e)),
  });

  if (error) return <ErrorBlock error={error} retry={refetch} />;
  if (isLoading || !data) return <LoadingBlock rows={5} />;

  const homes = (ids: number[]) =>
    ids.length === 0 ? "All homes" : ids.length === 1 ? (listings?.find((l) => l.id === ids[0])?.name ?? "1 home") : plural(ids.length, "home");
  const cats = CATEGORIES.filter((c) => data.some((a) => a.category === c)).concat([...new Set(data.map((a) => a.category))].filter((c) => !CATEGORIES.includes(c)));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-[14px] text-ink-2">
          Extras guests can add when booking on the web, by replying to an SMS (BREAKFAST, EARLY, LATE) or later from their trip page. Add-ons that need your
          OK — like early check-in — arrive as requests.
        </p>
        <Button variant="dark" onClick={() => setEditing("new")}>
          <Plus className="size-4" /> New add-on
        </Button>
      </div>

      {data.length === 0 ? (
        <EmptyState title="No add-ons yet" action={<Button onClick={() => setEditing("new")}>Create one</Button>}>
          Breakfast, airport pickup and late checkout are the favourites.
        </EmptyState>
      ) : (
        cats.map((cat) => (
          <section key={cat}>
            <h2 className="mb-2.5 text-[12px] font-bold tracking-wider text-ink-2 uppercase">{humanize(cat)}</h2>
            <ul className="grid gap-3 lg:grid-cols-2">
              {data
                .filter((a) => a.category === cat)
                .map((a) => (
                  <li key={a.id} className={cn("flex gap-4 rounded-2xl border border-line-soft bg-white p-4", !a.active && "opacity-60")}>
                    <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-surface">
                      <Icon name={a.icon} className="size-5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="flex flex-wrap items-center gap-2 text-[15px] font-semibold">
                        {a.name}
                        {a.requires_approval && <Badge tone="warning">Needs your OK</Badge>}
                      </p>
                      <p className="mt-0.5 line-clamp-2 text-[13px] text-ink-2">{a.short || a.description}</p>
                      <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-ink-2">
                        <span className="text-[14px] font-bold text-ink tabular-nums">{a.price ? kes(a.price) : "Free"}</span>
                        <span>{PRICING[a.pricing] ?? a.pricing}</span>
                        <span>·</span>
                        <span>{homes(a.unit_ids)}</span>
                        {a.lead_hours > 0 && <span>· {a.lead_hours}h notice</span>}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-2">
                      <Switch checked={a.active} onCheckedChange={() => toggle.mutate(a)} aria-label={`${a.name} on offer`} />
                      <div className="flex">
                        <IconButton label="Edit add-on" onClick={() => setEditing(a)}>
                          <Pencil />
                        </IconButton>
                        <IconButton label="Delete add-on" tone="danger" onClick={() => setRemoving(a)}>
                          <Trash2 />
                        </IconButton>
                      </div>
                    </div>
                  </li>
                ))}
            </ul>
          </section>
        ))
      )}

      <Dialog open={editing !== null} onOpenChange={(v) => !v && setEditing(null)}>
        {editing !== null && <AddonEditor addon={editing === "new" ? null : editing} onDone={() => setEditing(null)} />}
      </Dialog>

      <ConfirmDialog
        open={!!removing}
        onOpenChange={(v) => !v && setRemoving(null)}
        title={`Delete ${removing?.name ?? "add-on"}?`}
        confirmLabel="Delete"
        tone="danger"
        loading={remove.isPending}
        onConfirm={() => removing && remove.mutate(removing)}
      >
        It disappears from every booking flow. If guests have already booked it, switch it off instead — past bookings keep their add-ons.
      </ConfirmDialog>
    </div>
  );
}

function AddonEditor({ addon, onDone }: { addon: HostAddon | null; onDone: () => void }) {
  const invalidate = useInvalidateHost();
  const { data: listings } = useListings();
  const [d, setD] = React.useState(() => ({
    code: addon?.code ?? "",
    name: addon?.name ?? "",
    short: addon?.short ?? "",
    description: addon?.description ?? "",
    category: addon?.category ?? "comfort",
    icon: addon?.icon ?? "sparkles",
    price: addon?.price ?? (null as number | null),
    pricing: addon?.pricing ?? "per_stay",
    requires_approval: addon?.requires_approval ?? false,
    lead_hours: addon?.lead_hours ?? 0,
    active: addon?.active ?? true,
    sort_order: addon?.sort_order ?? 0,
    unit_ids: addon?.unit_ids ?? [],
  }));
  const [options, setOptions] = React.useState(() => JSON.stringify(addon?.options ?? {}, null, 2));
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [saving, setSaving] = React.useState(false);

  let parsed: Record<string, unknown> | null = null;
  let optionsError = "";
  try {
    const v = options.trim() ? JSON.parse(options) : {};
    if (v && typeof v === "object" && !Array.isArray(v)) parsed = v;
    else optionsError = "Options must be a JSON object, e.g. {\"time\": \"14:00\"}.";
  } catch {
    optionsError = "That isn't valid JSON yet.";
  }

  const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40);

  const save = async () => {
    if (!parsed) return;
    setSaving(true);
    setErrors({});
    const body = { ...d, code: d.code || slug(d.name), options: parsed };
    try {
      if (addon) await patch(`/api/host/addons/${addon.id}`, body);
      else await post("/api/host/addons", body);
      toast.success(addon ? "Add-on updated" : `${d.name} added`, { description: "Guests see it on the website, by SMS and on their trip page." });
      invalidate();
      onDone();
    } catch (e) {
      setErrors(fieldErrors(e));
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const all = listings ?? [];
  return (
    <DialogContent
      title={addon ? `Edit ${addon.name}` : "New add-on"}
      size="lg"
      footer={
        <div className="flex items-center justify-between gap-3">
          <label className="flex items-center gap-2.5 text-[14px] font-medium">
            <Switch checked={d.active} onCheckedChange={(v) => setD({ ...d, active: v })} aria-label="On offer" /> On offer
          </label>
          <Button variant="dark" onClick={save} loading={saving} disabled={!d.name.trim() || d.price === null || !!optionsError}>
            {addon ? "Save add-on" : "Create add-on"}
          </Button>
        </div>
      }
    >
      <div className="space-y-5 px-6 py-5">
        <div className="flex gap-4">
          <IconPicker value={d.icon} onChange={(icon) => setD({ ...d, icon })} />
          <div className="grid min-w-0 flex-1 gap-3 sm:grid-cols-2">
            <Field label="Name" error={errors.name}>
              <Input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} placeholder="Airport pickup" maxLength={60} />
            </Field>
            <Field label="Code" error={errors.code} hint={addon ? "Used by SMS keywords and reports — can't change." : "Leave blank to generate from the name."}>
              <Input value={d.code} onChange={(e) => setD({ ...d, code: slug(e.target.value) })} placeholder={slug(d.name) || "airport_pickup"} className="font-mono" disabled={!!addon} />
            </Field>
          </div>
        </div>
        <Field label="One-liner" error={errors.short} hint="Shown on the booking page and in SMS menus.">
          <Input value={d.short} onChange={(e) => setD({ ...d, short: e.target.value })} maxLength={120} placeholder="Meet & greet at Moi International Airport" />
        </Field>
        <Field label="Description" error={errors.description}>
          <Textarea value={d.description} onChange={(e) => setD({ ...d, description: e.target.value })} rows={3} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Category" error={errors.category}>
            <Select value={d.category} onChange={(e) => setD({ ...d, category: e.target.value })}>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {humanize(c)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Price" error={errors.price}>
            <NumberInput before="KES" value={d.price} onValueChange={(v) => setD({ ...d, price: v })} />
          </Field>
          <Field label="Charged" error={errors.pricing}>
            <Select value={d.pricing} onChange={(e) => setD({ ...d, pricing: e.target.value })}>
              {Object.entries(PRICING).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Notice needed" error={errors.lead_hours} hint="0 = can be added any time.">
            <NumberInput after="hours" value={d.lead_hours} onValueChange={(v) => setD({ ...d, lead_hours: v ?? 0 })} />
          </Field>
          <Field label="Sort order" error={errors.sort_order} hint="Lower numbers are shown first.">
            <NumberInput value={d.sort_order} onValueChange={(v) => setD({ ...d, sort_order: v ?? 0 })} />
          </Field>
        </div>
        <div className="rounded-xl border border-line-soft p-4">
          <SwitchRow
            label="Needs your OK"
            description="For things that depend on the calendar (early check-in, late checkout). Guests request it; you approve or decline and they're told by SMS."
            checked={d.requires_approval}
            onCheckedChange={(v) => setD({ ...d, requires_approval: v })}
          />
        </div>
        <div>
          <p className="mb-2 text-[13px] font-semibold">Offered at</p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setD({ ...d, unit_ids: [] })}
              className={cn("rounded-full border px-3 py-1.5 text-[13px] font-semibold", d.unit_ids.length === 0 ? "border-ink bg-ink text-white" : "border-line text-ink-2 hover:border-ink-3")}
            >
              All homes
            </button>
            {all.map((l) => {
              const on = d.unit_ids.includes(l.id);
              return (
                <button
                  key={l.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setD({ ...d, unit_ids: on ? d.unit_ids.filter((x) => x !== l.id) : [...d.unit_ids, l.id] })}
                  className={cn("rounded-full border px-3 py-1.5 text-[13px] font-semibold", on ? "border-ink bg-ink text-white" : "border-line text-ink-2 hover:border-ink-3")}
                >
                  {l.name}
                </button>
              );
            })}
          </div>
        </div>
        <Field label="Options (advanced)" error={optionsError || errors.options} hint='JSON the booking flow reads, e.g. {"time": "14:00"} or {"fields": ["flight", "time"]}.'>
          <Textarea value={options} onChange={(e) => setOptions(e.target.value)} rows={4} className="font-mono text-[13px]" spellCheck={false} />
        </Field>
      </div>
    </DialogContent>
  );
}
