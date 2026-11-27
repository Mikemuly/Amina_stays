"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Compass, ExternalLink, Link2, MapPin, Pencil, Plus, Search, Star, Ticket, Trash2, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { ErrorBlock, LoadingBlock, PageHeader } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Icon3D, type Icon3DName } from "@/components/ui/icon3d";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Badge, EmptyState } from "@/components/ui/misc";
import { Switch, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/overlays";
import { del, get, patch, post } from "@/lib/api";
import { fmtDate, fmtRange, plural, relDay } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useAreas, useInvalidateHost } from "./queries";
import type { HostAddon, HostGuideEvent, HostPlace, PlaceCategory } from "./types";
import { Callout, CharCount, ConfirmDialog, Field, IconButton, NumberInput, Segmented, SwitchRow, errorMessage, fieldErrors, useTabParam } from "./ui";

const CATEGORIES: { value: PlaceCategory; label: string; icon: Icon3DName }[] = [
  { value: "sights", label: "Sights & history", icon: "classical-building" },
  { value: "beaches", label: "Beaches & sea", icon: "beach" },
  { value: "nature", label: "Nature & wildlife", icon: "palm-tree" },
  { value: "food", label: "Food & drink", icon: "cooking" },
  { value: "markets", label: "Markets & crafts", icon: "shopping-cart" },
  { value: "culture", label: "Culture & faith", icon: "sparkles" },
  { value: "evenings", label: "Evenings out", icon: "sunset" },
  { value: "transport", label: "Getting around", icon: "train" },
  { value: "essentials", label: "Health & essentials", icon: "shield" },
];
const CATEGORY_OF = Object.fromEntries(CATEGORIES.map((c) => [c.value, c])) as Record<PlaceCategory, (typeof CATEGORIES)[number]>;
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const PLACES_KEY = ["host", "guide", "places"];
const EVENTS_KEY = ["host", "guide", "events"];
const TABS = ["places", "events"] as const;

function usePlaces() {
  return useQuery({ queryKey: PLACES_KEY, queryFn: () => get<HostPlace[]>("/api/host/guide/places") });
}
function useEvents() {
  return useQuery({ queryKey: EVENTS_KEY, queryFn: () => get<HostGuideEvent[]>("/api/host/guide/events") });
}
function useAreaName() {
  const { data: areas } = useAreas();
  return React.useCallback((slug: string | null) => (slug ? (areas?.find((a) => a.slug === slug)?.name ?? slug) : ""), [areas]);
}

/** PATCH one row of a list query, showing the change at once and rolling back if the server says no. */
function useRowPatch<T extends { id: number }>(key: string[], url: (id: number) => string, message: (row: T, body: Partial<T>) => string) {
  const qc = useQueryClient();
  const invalidate = useInvalidateHost();
  return useMutation({
    mutationFn: ({ row, body }: { row: T; body: Partial<T> }) => patch<T>(url(row.id), body),
    onMutate: async ({ row, body }) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData<T[]>(key);
      qc.setQueryData<T[]>(key, (old) => old?.map((x) => (x.id === row.id ? { ...x, ...body } : x)));
      return { prev };
    },
    onSuccess: (row, { body }) => toast.success(message(row, body)),
    onError: (e, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(key, ctx.prev);
      toast.error(errorMessage(e));
    },
    onSettled: () => invalidate(),
  });
}

export function GuidePage() {
  const [tab, setTab] = useTabParam(TABS, "places");
  const { data: places } = usePlaces();
  const { data: events } = useEvents();
  return (
    <>
      <PageHeader
        title="Local guide"
        subtitle="The places and events guests get on USSD, SMS, voice and the website — so a guest with no data knows the coast like a local."
        actions={
          <Button asChild variant="soft">
            <Link href="/guide" target="_blank">
              <ExternalLink className="size-4" /> Public guide
            </Link>
          </Button>
        }
      />
      <Callout tone="info" icon={<Compass className="size-[18px]" />} title="Guests get this guide with no data" className="mb-6">
        On USSD under More → Explore, by texting <Kw>EXPLORE</Kw>, <Kw>EVENTS</Kw> or a category like <Kw>FOOD</Kw>, or by pressing 6 on a call. The website shows it
        at{" "}
        <Link href="/guide" target="_blank" className="font-semibold text-ink underline underline-offset-2">
          /guide
        </Link>
        . The one-line summary is what fits on a phone screen, so keep it under 110 characters.
      </Callout>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="no-scrollbar mb-6 overflow-x-auto">
          <TabsTrigger value="places" className="flex shrink-0 items-center gap-2">
            Places {places && <Count n={places.length} />}
          </TabsTrigger>
          <TabsTrigger value="events" className="flex shrink-0 items-center gap-2">
            Events {events && <Count n={events.length} />}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="places" className="outline-none">
          <PlacesTab />
        </TabsContent>
        <TabsContent value="events" className="outline-none">
          <EventsTab />
        </TabsContent>
      </Tabs>
    </>
  );
}

function Kw({ children }: { children: React.ReactNode }) {
  return <span className="rounded bg-white/80 px-1 font-mono text-[12.5px] font-semibold text-ink ring-1 ring-line-soft">{children}</span>;
}

function Count({ n }: { n: number }) {
  return <span className="min-w-5 rounded-full bg-surface px-1.5 text-center text-[11px] leading-5 font-bold text-ink-2 tabular-nums">{n}</span>;
}

// ---------- places ----------

function PlacesTab() {
  const invalidate = useInvalidateHost();
  const { data, isLoading, error, refetch } = usePlaces();
  const areaName = useAreaName();
  const [cat, setCat] = React.useState<PlaceCategory | "all">("all");
  const [q, setQ] = React.useState("");
  const [editing, setEditing] = React.useState<HostPlace | "new" | null>(null);
  const [removing, setRemoving] = React.useState<HostPlace | null>(null);

  const toggle = useRowPatch<HostPlace>(PLACES_KEY, (id) => `/api/host/guide/places/${id}`, (p, body) =>
    body.featured !== undefined
      ? p.featured
        ? `${p.name} is a top pick — listed first everywhere`
        : `${p.name} is no longer a top pick`
      : p.active
        ? `${p.name} is back in the guide`
        : `${p.name} is hidden from guests`,
  );
  const remove = useMutation({
    mutationFn: (p: HostPlace) => del(`/api/host/guide/places/${p.id}`),
    onSuccess: (_r, p) => {
      toast.success(`${p.name} deleted`);
      setRemoving(null);
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (error) return <ErrorBlock error={error} retry={refetch} />;
  if (isLoading || !data) return <LoadingBlock rows={6} />;

  const needle = q.trim().toLowerCase();
  const matches = data.filter((p) => !needle || [p.name, p.summary, p.summary_sw, areaName(p.area)].some((x) => x.toLowerCase().includes(needle)));
  const shown = matches.filter((p) => cat === "all" || p.category === cat);
  const groups = CATEGORIES.map((c) => ({ ...c, items: shown.filter((p) => p.category === c.value) })).filter((g) => g.items.length > 0);
  const hits = data.reduce((s, p) => s + p.hits, 0);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <p className="mr-auto text-[13.5px] text-ink-2">
          {plural(data.filter((p) => p.active).length, "place")} live · {data.filter((p) => p.featured).length} top picks · opened {plural(hits, "time")} by USSD, SMS
          and voice
        </p>
        <div className="relative w-full sm:w-60">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search places" aria-label="Search places" className="h-10 pr-8 pl-9 text-sm" />
          {q && (
            <button type="button" aria-label="Clear search" onClick={() => setQ("")} className="absolute inset-y-0 right-1.5 my-auto grid size-7 place-items-center rounded-full text-ink-2 hover:bg-surface">
              <X className="size-3.5" />
            </button>
          )}
        </div>
        <Button variant="dark" onClick={() => setEditing("new")} className="w-full sm:w-auto">
          <Plus className="size-4" /> Add place
        </Button>
      </div>

      <div role="radiogroup" aria-label="Category" className="no-scrollbar -mx-5 flex gap-2 overflow-x-auto px-5 sm:mx-0 sm:flex-wrap sm:px-0">
        {[{ value: "all" as const, label: "All", icon: null }, ...CATEGORIES].map((c) => {
          const on = cat === c.value;
          const n = c.value === "all" ? matches.length : matches.filter((p) => p.category === c.value).length;
          return (
            <button
              key={c.value}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => setCat(c.value)}
              className={cn(
                "inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border px-3 text-[13px] font-semibold whitespace-nowrap transition",
                on ? "border-ink bg-ink text-white" : "border-line text-ink-2 hover:border-ink-3 hover:text-ink",
              )}
            >
              {c.icon && <Icon3D name={c.icon} size={18} />}
              {c.label}
              <span className={cn("tabular-nums", on ? "text-white/70" : "text-ink-3")}>{n}</span>
            </button>
          );
        })}
      </div>

      {groups.length === 0 ? (
        <EmptyState icon={<MapPin className="size-5" />} title={data.length ? "No places match" : "No places yet"} action={!data.length && <Button onClick={() => setEditing("new")}>Add the first place</Button>}>
          {data.length ? "Try another search or category." : "Add the beaches, sights and restaurants you'd send a friend to — guests get them by USSD, SMS and voice."}
        </EmptyState>
      ) : (
        groups.map((g) => (
          <section key={g.value} aria-labelledby={`cat-${g.value}`}>
            <h2 id={`cat-${g.value}`} className="mb-2.5 flex items-center gap-2 text-[12px] font-bold tracking-wider text-ink-2 uppercase">
              <Icon3D name={g.icon} size={20} />
              {g.label}
              <span className="font-semibold text-ink-3 tabular-nums">{g.items.length}</span>
            </h2>
            <ul className="grid gap-3 lg:grid-cols-2">
              {g.items.map((p) => (
                <PlaceCard
                  key={p.id}
                  p={p}
                  area={areaName(p.area)}
                  onFeatured={() => toggle.mutate({ row: p, body: { featured: !p.featured } })}
                  onActive={() => toggle.mutate({ row: p, body: { active: !p.active } })}
                  onEdit={() => setEditing(p)}
                  onDelete={() => setRemoving(p)}
                />
              ))}
            </ul>
          </section>
        ))
      )}

      <Dialog open={editing !== null} onOpenChange={(v) => !v && setEditing(null)}>
        {editing !== null && <PlaceEditor place={editing === "new" ? null : editing} defaultCategory={cat === "all" ? "sights" : cat} onDone={() => setEditing(null)} />}
      </Dialog>

      <ConfirmDialog
        open={!!removing}
        onOpenChange={(v) => !v && setRemoving(null)}
        title={`Delete ${removing?.name ?? "place"}?`}
        confirmLabel="Delete"
        tone="danger"
        loading={remove.isPending}
        onConfirm={() => removing && remove.mutate(removing)}
      >
        It disappears from USSD, SMS, voice and the website{removing?.hits ? `, and its ${plural(removing.hits, "visit")} are lost` : ""}. Events held there keep their
        date but lose the place. To take it out for a while, switch it off instead.
      </ConfirmDialog>
    </div>
  );
}

function PlaceThumb({ p }: { p: HostPlace }) {
  if (p.photo) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={p.photo} alt="" className="size-12 shrink-0 rounded-xl object-cover" loading="lazy" />;
  }
  return (
    <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-surface">
      <Icon3D name={CATEGORY_OF[p.category]?.icon ?? "pushpin"} size={28} />
    </span>
  );
}

function PlaceCard({
  p, area, onFeatured, onActive, onEdit, onDelete,
}: { p: HostPlace; area: string; onFeatured: () => void; onActive: () => void; onEdit: () => void; onDelete: () => void }) {
  return (
    <li className={cn("flex gap-3 rounded-2xl border border-line-soft bg-white p-4 sm:gap-4", !p.active && "bg-surface/60")}>
      <PlaceThumb p={p} />
      <div className="min-w-0 flex-1">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className={cn("text-[15px] font-semibold [overflow-wrap:anywhere]", !p.active && "text-ink-2")}>{p.name}</span>
              {p.featured && (
                <Badge tone="brand">
                  <Star className="size-3 fill-current" /> Top pick
                </Badge>
              )}
              {!p.active && <Badge>Hidden</Badge>}
            </p>
            <p className="mt-0.5 text-[12.5px] text-ink-2 [overflow-wrap:anywhere]">{[area || "Coast-wide", p.hours, p.price].filter(Boolean).join(" · ")}</p>
          </div>
          <div className="-mt-1 -mr-1 flex shrink-0 items-center gap-1">
            <IconButton label={p.featured ? "Remove from top picks" : "Make it a top pick"} onClick={onFeatured} aria-pressed={p.featured}>
              <Star className={cn(p.featured && "fill-ink text-ink")} />
            </IconButton>
            <Switch checked={p.active} onCheckedChange={onActive} aria-label={`${p.name}: shown to guests`} />
          </div>
        </div>
        <p className="mt-2 text-[14px] leading-snug text-ink [overflow-wrap:anywhere]">{p.summary}</p>
        <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[12.5px] text-ink-2">
          <CharCount value={p.summary} max={110} />
          <span className={cn(p.hits ? "font-semibold text-ink" : "text-ink-3")}>{p.hits ? `Asked ${plural(p.hits, "time")}` : "Not asked yet"}</span>
          {!p.summary_sw && <span className="text-warning">No Kiswahili line</span>}
          <a href={p.map_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold text-ink hover:underline">
            <MapPin className="size-3.5" /> Map
          </a>
          <span className="ml-auto flex">
            <IconButton label={`Edit ${p.name}`} onClick={onEdit}>
              <Pencil />
            </IconButton>
            <IconButton label={`Delete ${p.name}`} tone="danger" onClick={onDelete}>
              <Trash2 />
            </IconButton>
          </span>
        </div>
      </div>
    </li>
  );
}

type PlaceForm = Omit<HostPlace, "id" | "slug" | "category_label" | "hits" | "map_url" | "updated_at" | "area"> & { area: string };

function PlaceEditor({ place, defaultCategory, onDone }: { place: HostPlace | null; defaultCategory: PlaceCategory; onDone: () => void }) {
  const invalidate = useInvalidateHost();
  const { data: areas } = useAreas();
  const [d, setD] = React.useState<PlaceForm>(() => ({
    name: place?.name ?? "",
    category: place?.category ?? defaultCategory,
    area: place?.area ?? "",
    summary: place?.summary ?? "",
    summary_sw: place?.summary_sw ?? "",
    description: place?.description ?? "",
    tips: place?.tips ?? "",
    hours: place?.hours ?? "",
    price: place?.price ?? "",
    phone: place?.phone ?? "",
    website: place?.website ?? "",
    latitude: place?.latitude ?? null,
    longitude: place?.longitude ?? null,
    photo: place?.photo ?? "",
    featured: place?.featured ?? false,
    active: place?.active ?? true,
    sort_order: place?.sort_order ?? 0,
  }));
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const set = <K extends keyof PlaceForm>(k: K, v: PlaceForm[K]) => {
    setD((x) => ({ ...x, [k]: v }));
    if (errors[k]) setErrors((e) => Object.fromEntries(Object.entries(e).filter(([key]) => key !== k)));
  };
  const coordsError = (d.latitude === null) !== (d.longitude === null) ? "Give both a latitude and a longitude, or neither." : "";

  const save = useMutation({
    mutationFn: () => {
      const body = { ...d, name: d.name.trim(), summary: d.summary.trim(), summary_sw: d.summary_sw.trim(), area: d.area || null, website: d.website.trim(), photo: d.photo.trim() };
      return place ? patch<HostPlace>(`/api/host/guide/places/${place.id}`, body) : post<HostPlace>("/api/host/guide/places", body);
    },
    onSuccess: (r) => {
      toast.success(place ? `${r.name} saved` : `${r.name} added to the guide`, { description: "Guests get it on USSD, SMS, voice and the website straight away." });
      invalidate();
      onDone();
    },
    onError: (e) => {
      setErrors(fieldErrors(e));
      toast.error(errorMessage(e));
    },
  });

  return (
    <DialogContent
      title={place ? `Edit ${place.name}` : "Add a place"}
      size="lg"
      footer={
        <div className="flex flex-wrap items-center justify-between gap-3">
          <label className="flex items-center gap-2.5 text-[14px] font-medium">
            <Switch checked={d.active} onCheckedChange={(v) => set("active", v)} aria-label="Shown to guests" /> Shown to guests
          </label>
          <Button variant="dark" onClick={() => save.mutate()} loading={save.isPending} disabled={!d.name.trim() || !d.summary.trim() || !!coordsError}>
            {place ? "Save place" : "Add place"}
          </Button>
        </div>
      }
    >
      <form
        className="space-y-5 px-6 py-5"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name" error={errors.name} className="sm:col-span-2">
            <Input value={d.name} onChange={(e) => set("name", e.target.value)} maxLength={80} placeholder="Fort Jesus" autoFocus={!place} />
          </Field>
          <Field label="Category" error={errors.category}>
            <Select value={d.category} onChange={(e) => set("category", e.target.value as PlaceCategory)}>
              {CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Area" error={errors.area}>
            <Select value={d.area} onChange={(e) => set("area", e.target.value)}>
              <option value="">Coast-wide / no one area</option>
              {(areas ?? []).map((a) => (
                <option key={a.slug} value={a.slug}>
                  {a.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <Field
          label={
            <span className="flex items-center justify-between gap-3">
              One-line summary <CharCount value={d.summary} max={110} />
            </span>
          }
          error={errors.summary}
          hint="What guests see on USSD and SMS, so it has to stand on its own."
        >
          <Input value={d.summary} onChange={(e) => set("summary", e.target.value)} maxLength={110} placeholder="16th-century Portuguese fort and museum on the Old Town waterfront." />
        </Field>
        <Field
          label={
            <span className="flex items-center justify-between gap-3">
              The same line in Kiswahili <CharCount value={d.summary_sw} max={110} />
            </span>
          }
          error={errors.summary_sw}
          hint="Sent to guests who use the service in Kiswahili. Left blank, they get the English line."
        >
          <Input value={d.summary_sw} onChange={(e) => set("summary_sw", e.target.value)} maxLength={110} placeholder="Ngome ya Kireno ya karne ya 16 na makumbusho ufukweni mwa Mji wa Kale." />
        </Field>
        <Field label="Description" error={errors.description} hint="The longer story, shown on the website.">
          <Textarea value={d.description} onChange={(e) => set("description", e.target.value)} rows={3} />
        </Field>
        <Field
          label={
            <span className="flex items-center justify-between gap-3">
              Tips <CharCount value={d.tips} max={240} />
            </span>
          }
          error={errors.tips}
          hint="Etiquette, safety, the best time to go — sent when a guest asks for more."
        >
          <Textarea value={d.tips} onChange={(e) => set("tips", e.target.value)} rows={2} maxLength={240} className="min-h-16" />
        </Field>

        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Opening hours" error={errors.hours}>
            <Input value={d.hours} onChange={(e) => set("hours", e.target.value)} maxLength={80} placeholder="Daily 8am–6pm" />
          </Field>
          <Field label="Price" error={errors.price}>
            <Input value={d.price} onChange={(e) => set("price", e.target.value)} maxLength={100} placeholder="KES 1,200 for visitors" />
          </Field>
          <Field label="Phone" error={errors.phone}>
            <Input type="tel" value={d.phone} onChange={(e) => set("phone", e.target.value)} maxLength={20} placeholder="+254 …" />
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Website" error={errors.website}>
            <Input type="url" value={d.website} onChange={(e) => set("website", e.target.value)} placeholder="https://…" />
          </Field>
          <Field label="Photo URL" error={errors.photo}>
            <Input type="url" value={d.photo} onChange={(e) => set("photo", e.target.value)} placeholder="https://images.unsplash.com/…" />
          </Field>
        </div>
        <div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Latitude" error={errors.latitude}>
              <NumberInput decimal value={d.latitude} onValueChange={(v) => set("latitude", v)} placeholder="-4.0629" />
            </Field>
            <Field label="Longitude" error={errors.longitude}>
              <NumberInput decimal value={d.longitude} onValueChange={(v) => set("longitude", v)} placeholder="39.6797" />
            </Field>
          </div>
          <p className={cn("mt-1.5 text-[13px]", coordsError ? "text-danger" : "text-ink-2")}>
            {coordsError || "Both or neither. Used to show guests what's closest to their home; the map link searches by name."}
          </p>
        </div>
        <div className="grid items-start gap-4 sm:grid-cols-[minmax(0,1fr)_140px]">
          <div className="rounded-xl border border-line-soft p-4">
            <SwitchRow
              label="Top pick"
              description="Listed first in its category on every channel, and on the home's listing page."
              checked={d.featured}
              onCheckedChange={(v) => set("featured", v)}
            />
          </div>
          <Field label="Sort order" error={errors.sort_order} hint="Lower comes first.">
            <NumberInput value={d.sort_order} onValueChange={(v) => set("sort_order", Math.max(0, v ?? 0))} />
          </Field>
        </div>
        <button type="submit" hidden />
      </form>
    </DialogContent>
  );
}

// ---------- events ----------

function schedule(e: HostGuideEvent) {
  if (e.weekday !== null) return `Every ${WEEKDAYS[e.weekday] ?? "week"}`;
  if (!e.starts_on) return "No date set";
  const single = !e.ends_on || e.ends_on === e.starts_on;
  if (e.yearly) return `${single ? fmtDate(e.starts_on, "d MMMM") : fmtRange(e.starts_on, e.ends_on)} · every year`;
  return single ? fmtDate(e.starts_on, "EEE d MMM yyyy") : `${fmtRange(e.starts_on, e.ends_on)} ${fmtDate(e.ends_on, "yyyy")}`;
}

function DateTile({ on }: { on: string | null }) {
  if (!on) {
    return (
      <span className="grid size-14 shrink-0 place-items-center rounded-xl border border-line-soft bg-surface text-[11px] font-semibold text-ink-3 uppercase">Over</span>
    );
  }
  return (
    <span className="flex size-14 shrink-0 flex-col items-center justify-center rounded-xl border border-line-soft bg-white leading-none">
      <span className="text-[10.5px] font-bold tracking-wide text-brand-600 uppercase">{fmtDate(on, "EEE")}</span>
      <span className="mt-0.5 text-[20px] font-semibold tabular-nums">{fmtDate(on, "d")}</span>
      <span className="mt-0.5 text-[10.5px] font-medium text-ink-2">{fmtDate(on, "MMM")}</span>
    </span>
  );
}

function EventsTab() {
  const invalidate = useInvalidateHost();
  const { data, isLoading, error, refetch } = useEvents();
  const { data: places } = usePlaces();
  const areaName = useAreaName();
  const [editing, setEditing] = React.useState<HostGuideEvent | "new" | null>(null);
  const [removing, setRemoving] = React.useState<HostGuideEvent | null>(null);
  const toggle = useRowPatch<HostGuideEvent>(EVENTS_KEY, (id) => `/api/host/guide/events/${id}`, (e) => (e.active ? `${e.title} is back in the guide` : `${e.title} is hidden from guests`));
  const remove = useMutation({
    mutationFn: (e: HostGuideEvent) => del(`/api/host/guide/events/${e.id}`),
    onSuccess: (_r, e) => {
      toast.success(`${e.title} deleted`);
      setRemoving(null);
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (error) return <ErrorBlock error={error} retry={refetch} />;
  if (isLoading || !data) return <LoadingBlock rows={5} />;

  const sorted = [...data].sort(
    (a, b) => Number(b.active) - Number(a.active) || (a.next_on ?? "9999").localeCompare(b.next_on ?? "9999") || a.title.localeCompare(b.title),
  );
  const placeName = (id: number | null) => (id ? places?.find((p) => p.id === id)?.name : undefined);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <p className="mr-auto text-[13.5px] text-ink-2">
          Weekly happenings and dated events. Guests see what&apos;s on in the next two weeks — texting <Kw>EVENTS</Kw> gets the next few.
        </p>
        <Button variant="dark" onClick={() => setEditing("new")} className="w-full sm:w-auto">
          <Plus className="size-4" /> Add event
        </Button>
      </div>

      {sorted.length === 0 ? (
        <EmptyState icon={<CalendarDays className="size-5" />} title="No events yet" action={<Button onClick={() => setEditing("new")}>Add the first event</Button>}>
          Market days, a weekly dhow cruise, festivals and public holidays.
        </EmptyState>
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {sorted.map((e) => {
            const where = [placeName(e.place), areaName(e.area)].filter(Boolean).join(", ");
            return (
              <li key={e.id} className={cn("flex gap-3 rounded-2xl border border-line-soft bg-white p-4 sm:gap-4", !e.active && "bg-surface/60")}>
                <DateTile on={e.active ? e.next_on : null} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span className={cn("text-[15px] font-semibold [overflow-wrap:anywhere]", !e.active && "text-ink-2")}>{e.title}</span>
                        {e.addon_code && (
                          <Badge tone="ocean">
                            <Ticket className="size-3" /> Bookable extra
                          </Badge>
                        )}
                        {!e.active && <Badge>Hidden</Badge>}
                      </p>
                      <p className="mt-0.5 text-[13px] font-medium text-ink">
                        {schedule(e)}
                        {e.time && <span className="font-normal text-ink-2"> · {e.time}</span>}
                      </p>
                    </div>
                    <Switch checked={e.active} onCheckedChange={() => toggle.mutate({ row: e, body: { active: !e.active } })} aria-label={`${e.title}: shown to guests`} />
                  </div>
                  {e.summary && <p className="mt-1.5 text-[13.5px] leading-snug text-ink-2 [overflow-wrap:anywhere]">{e.summary}</p>}
                  <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[12.5px] text-ink-2">
                    <span className={cn("font-semibold", e.next_on && e.active ? "text-ink" : "text-ink-3")}>
                      {!e.active ? "Not shown" : e.next_on ? `Next: ${relDay(e.next_on)}` : "Over — no upcoming date"}
                    </span>
                    {where && (
                      <span className="inline-flex min-w-0 items-center gap-1">
                        <MapPin className="size-3.5 shrink-0" /> <span className="[overflow-wrap:anywhere]">{where}</span>
                      </span>
                    )}
                    {e.price && <span className="[overflow-wrap:anywhere]">{e.price}</span>}
                    {e.link && (
                      <a href={e.link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-semibold text-ink hover:underline">
                        <Link2 className="size-3.5" /> Link
                      </a>
                    )}
                    <span className="ml-auto flex">
                      <IconButton label={`Edit ${e.title}`} onClick={() => setEditing(e)}>
                        <Pencil />
                      </IconButton>
                      <IconButton label={`Delete ${e.title}`} tone="danger" onClick={() => setRemoving(e)}>
                        <Trash2 />
                      </IconButton>
                    </span>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <Dialog open={editing !== null} onOpenChange={(v) => !v && setEditing(null)}>
        {editing !== null && <EventEditor event={editing === "new" ? null : editing} places={places ?? []} onDone={() => setEditing(null)} />}
      </Dialog>

      <ConfirmDialog
        open={!!removing}
        onOpenChange={(v) => !v && setRemoving(null)}
        title={`Delete ${removing?.title ?? "event"}?`}
        confirmLabel="Delete"
        tone="danger"
        loading={remove.isPending}
        onConfirm={() => removing && remove.mutate(removing)}
      >
        It disappears from USSD, SMS, voice and the website. To skip it for a while, switch it off instead.
      </ConfirmDialog>
    </div>
  );
}

type Repeats = "weekly" | "dates";

function EventEditor({ event, places, onDone }: { event: HostGuideEvent | null; places: HostPlace[]; onDone: () => void }) {
  const invalidate = useInvalidateHost();
  const { data: areas } = useAreas();
  const { data: addons } = useQuery({ queryKey: ["host", "addons"], queryFn: () => get<HostAddon[]>("/api/host/addons") });
  const [d, setD] = React.useState(() => ({
    title: event?.title ?? "",
    summary: event?.summary ?? "",
    place: event?.place ?? null,
    area: event?.area ?? "",
    repeats: (event && event.weekday === null ? "dates" : "weekly") as Repeats,
    weekday: event?.weekday ?? 4,
    starts_on: event?.starts_on ?? "",
    ends_on: event?.ends_on ?? "",
    yearly: event?.yearly ?? false,
    time: event?.time ?? "",
    price: event?.price ?? "",
    addon_code: event?.addon_code ?? "",
    link: event?.link ?? "",
    active: event?.active ?? true,
  }));
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const set = <K extends keyof typeof d>(k: K, v: (typeof d)[K]) => {
    setD((x) => ({ ...x, [k]: v }));
    if (errors[k]) setErrors((e) => Object.fromEntries(Object.entries(e).filter(([key]) => key !== k)));
  };
  const weekly = d.repeats === "weekly";
  const datesError = !weekly && d.starts_on && d.ends_on && d.ends_on < d.starts_on ? "The end date is before the start date." : "";

  const save = useMutation({
    mutationFn: () => {
      const body = {
        title: d.title.trim(),
        summary: d.summary.trim(),
        place: d.place,
        area: d.area || null,
        weekday: weekly ? d.weekday : null,
        starts_on: weekly ? null : d.starts_on || null,
        ends_on: weekly ? null : d.ends_on || null,
        yearly: weekly ? false : d.yearly,
        time: d.time.trim(),
        price: d.price.trim(),
        addon_code: d.addon_code,
        link: d.link.trim(),
        active: d.active,
      };
      return event ? patch<HostGuideEvent>(`/api/host/guide/events/${event.id}`, body) : post<HostGuideEvent>("/api/host/guide/events", body);
    },
    onSuccess: (r) => {
      toast.success(event ? `${r.title} saved` : `${r.title} added`, { description: r.next_on ? `Next on ${relDay(r.next_on)}.` : "It has no upcoming date, so guests won't see it." });
      invalidate();
      onDone();
    },
    onError: (e) => {
      setErrors(fieldErrors(e));
      toast.error(errorMessage(e));
    },
  });

  const addonOptions = [...(addons ?? []).map((a) => ({ code: a.code, name: a.name }))];
  if (d.addon_code && !addonOptions.some((a) => a.code === d.addon_code)) addonOptions.push({ code: d.addon_code, name: d.addon_code });
  const ready = !!d.title.trim() && (weekly || !!d.starts_on) && !datesError;

  return (
    <DialogContent
      title={event ? `Edit ${event.title}` : "Add an event"}
      size="lg"
      footer={
        <div className="flex flex-wrap items-center justify-between gap-3">
          <label className="flex items-center gap-2.5 text-[14px] font-medium">
            <Switch checked={d.active} onCheckedChange={(v) => set("active", v)} aria-label="Shown to guests" /> Shown to guests
          </label>
          <Button variant="dark" onClick={() => save.mutate()} loading={save.isPending} disabled={!ready}>
            {event ? "Save event" : "Add event"}
          </Button>
        </div>
      }
    >
      <form
        className="space-y-5 px-6 py-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (ready) save.mutate();
        }}
      >
        <Field label="Title" error={errors.title}>
          <Input value={d.title} onChange={(e) => set("title", e.target.value)} maxLength={100} placeholder="Sunset dhow cruise on Tudor Creek" autoFocus={!event} />
        </Field>
        <Field
          label={
            <span className="flex items-center justify-between gap-3">
              One-line summary <CharCount value={d.summary} max={160} />
            </span>
          }
          error={errors.summary}
        >
          <Input value={d.summary} onChange={(e) => set("summary", e.target.value)} maxLength={160} placeholder="Sail out at golden hour with Swahili snacks and the Old Town skyline." />
        </Field>

        <div className="rounded-xl border border-line-soft p-4">
          <p className="mb-2 text-[13px] font-semibold">Repeats</p>
          <Segmented<Repeats>
            label="Repeats"
            value={d.repeats}
            onChange={(v) => set("repeats", v)}
            options={[
              { value: "weekly", label: "Every week" },
              { value: "dates", label: "On dates" },
            ]}
          />
          {weekly ? (
            <Field label="Day of the week" error={errors.weekday} className="mt-4 max-w-xs">
              <Select value={d.weekday} onChange={(e) => set("weekday", Number(e.target.value))}>
                {WEEKDAYS.map((w, i) => (
                  <option key={w} value={i}>
                    {w}
                  </option>
                ))}
              </Select>
            </Field>
          ) : (
            <div className="mt-4 space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Starts on" error={errors.starts_on}>
                  <Input type="date" value={d.starts_on} onChange={(e) => set("starts_on", e.target.value)} className="min-w-0" />
                </Field>
                <Field label="Ends on (optional)" error={errors.ends_on || datesError}>
                  <Input type="date" value={d.ends_on} min={d.starts_on || undefined} onChange={(e) => set("ends_on", e.target.value)} className="min-w-0" />
                </Field>
              </div>
              <label className="flex items-start gap-3 text-[14px]">
                <input type="checkbox" className="mt-0.5 size-4 accent-[#222]" checked={d.yearly} onChange={(e) => set("yearly", e.target.checked)} />
                <span>
                  <span className="font-semibold">Every year on these dates</span>
                  <span className="block text-[13px] text-ink-2">For festivals and public holidays like Jamhuri Day.</span>
                </span>
              </label>
            </div>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Time" error={errors.time} hint="As guests should read it.">
            <Input value={d.time} onChange={(e) => set("time", e.target.value)} maxLength={40} placeholder="5pm–7:30pm" />
          </Field>
          <Field label="Price" error={errors.price}>
            <Input value={d.price} onChange={(e) => set("price", e.target.value)} maxLength={100} placeholder="KES 4,500 — add it from your trip page" />
          </Field>
          <Field label="Place (optional)" error={errors.place}>
            <Select value={d.place ?? ""} onChange={(e) => set("place", e.target.value ? Number(e.target.value) : null)}>
              <option value="">Not at a listed place</option>
              {CATEGORIES.map((c) => {
                const items = places.filter((p) => p.category === c.value);
                return items.length ? (
                  <optgroup key={c.value} label={c.label}>
                    {items.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </optgroup>
                ) : null;
              })}
            </Select>
          </Field>
          <Field label="Area (optional)" error={errors.area} hint={d.place ? "Left blank, the place's area is used." : undefined}>
            <Select value={d.area} onChange={(e) => set("area", e.target.value)}>
              <option value="">{d.place ? "The place's area" : "Coast-wide"}</option>
              {(areas ?? []).map((a) => (
                <option key={a.slug} value={a.slug}>
                  {a.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Bookable as an extra (optional)" error={errors.addon_code} hint="Guests can add it from their trip page.">
            <Select value={d.addon_code} onChange={(e) => set("addon_code", e.target.value)}>
              <option value="">Not bookable</option>
              {addonOptions.map((a) => (
                <option key={a.code} value={a.code}>
                  {a.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Link (optional)" error={errors.link}>
            <Input type="url" value={d.link} onChange={(e) => set("link", e.target.value)} placeholder="https://…" />
          </Field>
        </div>
        <button type="submit" hidden />
      </form>
    </DialogContent>
  );
}
