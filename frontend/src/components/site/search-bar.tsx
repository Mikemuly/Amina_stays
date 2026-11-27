"use client";

import { useQuery } from "@tanstack/react-query";
import { addDays, isFriday, isSaturday, nextFriday, startOfToday } from "date-fns";
import { ChevronLeft, Search, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Dialog as D } from "radix-ui";
import * as React from "react";

import { hydrationSafe, useHydrated } from "@/components/providers";
import { GuestPicker, guestsLabel, type Guests } from "@/components/site/guest-picker";
import { RangeCalendar } from "@/components/site/range-calendar";
import { Button } from "@/components/ui/button";
import { Icon3D, type Icon3DName } from "@/components/ui/icon3d";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/overlays";
import { get } from "@/lib/api";
import { createBrowserStore, readStorage, writeStorage } from "@/lib/browser-store";
import { fmtRange, fmtShort, iso, toDate } from "@/lib/format";
import type { Area } from "@/lib/types";
import { cn } from "@/lib/utils";

export type SearchState = { area?: string; checkIn?: string; checkOut?: string } & Guests;
export type Segment = "where" | "dates" | "who";

/** Search-page filters that survive a new destination/date search from the header. */
export const FILTER_KEYS = ["tag", "type", "bedrooms", "amenities", "min_price", "max_price", "free_cancellation", "guest_favourite", "sort"] as const;

export function useSearchState(): SearchState {
  const p = useSearchParams();
  return {
    area: p.get("area") || undefined,
    checkIn: p.get("check_in") || undefined,
    checkOut: p.get("check_out") || undefined,
    adults: Number(p.get("adults") || 0) || (p.get("guests") ? Number(p.get("guests")) : 0),
    children: Number(p.get("children") || 0),
    infants: Number(p.get("infants") || 0),
  };
}

export function searchQuery(s: Partial<SearchState>, extra: Record<string, string | undefined> = {}) {
  const q = new URLSearchParams();
  if (s.area) q.set("area", s.area);
  if (s.checkIn && s.checkOut) {
    q.set("check_in", s.checkIn);
    q.set("check_out", s.checkOut);
  }
  if (s.adults) q.set("adults", String(s.adults));
  if (s.children) q.set("children", String(s.children));
  if (s.infants) q.set("infants", String(s.infants));
  Object.entries(extra).forEach(([k, v]) => v && q.set(k, v));
  const out = q.toString();
  return out ? `?${out}` : "";
}

// "Continue your search": the last search submitted from the header, remembered in this browser as on Airbnb.
const LAST_SEARCH_KEY = "amina:last-search";
const lastSearchStore = createBrowserStore(() => readStorage(LAST_SEARCH_KEY));

function saveLastSearch(s: SearchState) {
  if (!s.area && !s.checkIn && !s.adults && !s.children) return;
  const { area, checkIn, checkOut, adults, children, infants } = s;
  writeStorage(LAST_SEARCH_KEY, JSON.stringify({ area, checkIn, checkOut, adults, children, infants }));
  lastSearchStore.notify();
}

/** The guest's last search without any dates that have passed; null on the server and while hydrating. */
export function useLastSearch(): SearchState | null {
  const raw = React.useSyncExternalStore(lastSearchStore.subscribe, lastSearchStore.read, () => null);
  return React.useMemo(() => {
    if (!raw) return null;
    try {
      const s = JSON.parse(raw) as Partial<SearchState>;
      const out: SearchState = { area: s.area, adults: s.adults || 0, children: s.children || 0, infants: s.infants || 0 };
      if (s.checkIn && s.checkOut && s.checkIn >= iso(startOfToday())) Object.assign(out, { checkIn: s.checkIn, checkOut: s.checkOut });
      return out.area || out.checkIn || out.adults + out.children ? out : null;
    } catch {
      return null;
    }
  }, [raw]);
}

export function useAreas() {
  const q = useQuery({ queryKey: ["areas"], queryFn: () => get<Area[]>("/api/areas"), staleTime: 10 * 60_000 });
  // several Suspense boundaries read this; ones hydrating after the fetch must still match the server HTML
  return hydrationSafe(q, useHydrated());
}

// Illustrated tiles for each neighbourhood, in the style of the "Suggested destinations" list.
const AREA_STYLE: Record<string, { icon: Icon3DName; tint: string; tagline: string }> = {
  nyali: { icon: "beach", tint: "#e8f1ff", tagline: "Calm beaches & cafés" },
  diani: { icon: "palm-tree", tint: "#e9f7ec", tagline: "Prime beach spot" },
  "old-town": { icon: "door", tint: "#fff0e3", tagline: "Swahili heritage" },
  bamburi: { icon: "wave", tint: "#e4f5fa", tagline: "Family beaches" },
  mtwapa: { icon: "sailboat", tint: "#efebff", tagline: "Creek-side sunsets" },
};

export function areaStyle(a: Pick<Area, "slug" | "units_count">) {
  return AREA_STYLE[a.slug] ?? { icon: "pushpin" as Icon3DName, tint: "#f2f2f2", tagline: a.units_count ? `${a.units_count} homes` : "" };
}

export function whenLabel(s: Pick<SearchState, "checkIn" | "checkOut">, empty = "Add dates") {
  if (s.checkIn && s.checkOut) return fmtRange(s.checkIn, s.checkOut);
  if (s.checkIn) return `${fmtShort(s.checkIn)} – Add checkout`;
  return empty;
}

/** Local draft of the search, kept in sync with the URL, plus a submit that lands on /s. */
function useSearchDraft() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const fromUrl = useSearchState();
  const [s, setS] = React.useState<SearchState>(fromUrl);
  const paramsKey = params.toString();
  const [syncedKey, setSyncedKey] = React.useState(paramsKey);
  if (paramsKey !== syncedKey) {
    // back/forward or a filter change: reflect the URL's search in the bar
    setSyncedKey(paramsKey);
    setS(fromUrl);
  }
  const { data: areas } = useAreas();
  const submit = (next: SearchState = s) => {
    const keep: Record<string, string | undefined> = {};
    if (pathname === "/s") FILTER_KEYS.forEach((k) => (keep[k] = params.get(k) || undefined));
    saveLastSearch(next);
    router.push(`/s${searchQuery(next, keep)}`);
  };
  return { s, setS, submit, areas: areas ?? [], areaName: areas?.find((a) => a.slug === s.area)?.name };
}

function datePresets(s: SearchState): { label: string; range: [Date, Date] }[] {
  const today = startOfToday();
  const fri = isFriday(today) ? today : isSaturday(today) ? addDays(today, -1) : nextFriday(today);
  const start = s.checkIn ? toDate(s.checkIn) : addDays(today, 1);
  return [
    { label: "This weekend", range: [fri < today ? today : fri, addDays(fri, 2)] },
    { label: "Next weekend", range: [addDays(fri, 7), addDays(fri, 9)] },
    { label: "1 week", range: [start, addDays(start, 7)] },
    { label: "2 weeks", range: [start, addDays(start, 14)] },
  ];
}

// ---------------------------------------------------------------- desktop

export function SearchBar({ initial = null, onClose }: { initial?: Segment | null; onClose?: () => void }) {
  const { s, setS, submit, areas, areaName } = useSearchDraft();
  const [active, setActive] = React.useState<Segment | null>(initial);
  const [hover, setHover] = React.useState<Segment | null>(null);
  const [query, setQuery] = React.useState("");
  const barRef = React.useRef<HTMLDivElement>(null);
  const whereRef = React.useRef<HTMLInputElement>(null);

  const close = () => {
    setActive(null);
    onClose?.();
  };
  const go = () => {
    close();
    submit();
  };
  const open = (seg: Segment) => {
    setActive(seg);
    if (seg === "where") requestAnimationFrame(() => whereRef.current?.focus());
  };
  React.useEffect(() => {
    if (initial === "where") whereRef.current?.focus();
  }, [initial]);

  const matches = areas.filter((a) => !query || `${a.name} ${a.summary}`.toLowerCase().includes(query.toLowerCase()));
  const pickArea = (slug?: string) => {
    setS({ ...s, area: slug });
    setQuery("");
    setActive("dates");
  };
  const guestsSet = s.adults + s.children > 0;
  // separators vanish next to the active or hovered field, like a single sliding surface
  const sepHidden = (a: Segment, b: Segment) => [active, hover].some((x) => x === a || x === b);

  return (
    <Popover open={active !== null} onOpenChange={(o) => !o && close()}>
      <PopoverAnchor asChild>
        <div
          ref={barRef}
          role="search"
          onMouseLeave={() => setHover(null)}
          className={cn(
            "relative mx-auto flex h-[66px] w-full max-w-[850px] items-center rounded-full border border-line shadow-search transition-colors duration-200",
            active ? "bg-line-soft" : "bg-white",
          )}
        >
          <Field
            label="Where"
            active={active === "where"}
            barActive={!!active}
            onHover={() => setHover("where")}
            onClick={() => open("where")}
            className="flex-[1.15] pl-8"
          >
            {active === "where" ? (
              <input
                ref={whereRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && matches[0]) pickArea(matches[0].slug);
                }}
                placeholder={areaName ?? "Search destinations"}
                className="w-full truncate bg-transparent text-sm text-ink outline-none placeholder:text-ink-2"
                aria-label="Search destinations"
              />
            ) : (
              <span className={cn("block truncate text-sm", areaName ? "text-ink" : "text-ink-2")}>{areaName ?? "Search destinations"}</span>
            )}
          </Field>
          <Sep hidden={sepHidden("where", "dates")} />
          <Field label="When" active={active === "dates"} barActive={!!active} onHover={() => setHover("dates")} onClick={() => open("dates")} className="flex-1">
            <span className={cn("block truncate text-sm", s.checkIn ? "text-ink" : "text-ink-2")}>{whenLabel(s)}</span>
          </Field>
          <Sep hidden={sepHidden("dates", "who")} />
          <Field
            label="Who"
            active={active === "who"}
            barActive={!!active}
            onHover={() => setHover("who")}
            onClick={() => open("who")}
            className={cn("flex-1", active ? "pr-[132px]" : "pr-[72px]")}
          >
            <span className={cn("block truncate text-sm", guestsSet ? "text-ink" : "text-ink-2")}>{guestsLabel(s)}</span>
          </Field>
          {/* flat, deeper brand tone like Airbnb's #DA1249 search button; grows into a "Search" pill while a field is open */}
          <button
            type="button"
            onClick={go}
            aria-label="Search"
            className={cn(
              "absolute right-2 flex h-12 items-center justify-center gap-2 overflow-hidden rounded-full bg-brand-600 text-white transition-[width,background-color] duration-300 ease-[cubic-bezier(.2,0,0,1)] hover:bg-brand-700 active:scale-[0.96]",
              active ? "w-[104px] px-4" : "w-12",
            )}
          >
            <Search className="size-4 shrink-0" strokeWidth={3} />
            {active && <span className="text-base font-medium">Search</span>}
          </button>
        </div>
      </PopoverAnchor>
      <PopoverContent
        align={active === "who" ? "end" : active === "where" ? "start" : "center"}
        sideOffset={12}
        onOpenAutoFocus={(e) => e.preventDefault()}
        onInteractOutside={(e) => {
          if (barRef.current?.contains(e.target as Node)) e.preventDefault();
        }}
        className={cn(
          "rounded-[32px] border-0 shadow-pop animate-pop-in",
          active === "dates" ? "w-[min(850px,95vw)] px-8 pt-8 pb-6" : active === "who" ? "w-[425px] px-8 py-4" : "w-[425px] px-4 py-6",
        )}
      >
        {active === "where" && <WherePanel areas={matches} selected={s.area} onPick={pickArea} query={query} />}
        {active === "dates" && (
          <DatesPanel
            s={s}
            onChange={(r) => {
              setS({ ...s, checkIn: r.from, checkOut: r.to });
              if (r.from && r.to) setActive("who");
            }}
          />
        )}
        {active === "who" && <GuestPicker value={s} onChange={(g) => setS({ ...s, ...g })} max={6} />}
      </PopoverContent>
    </Popover>
  );
}

function Field({ label, active, barActive, onClick, onHover, className, children }: {
  label: string; active: boolean; barActive: boolean; onClick: () => void; onHover: () => void; className?: string; children: React.ReactNode;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && e.target === e.currentTarget && onClick()}
      onMouseEnter={onHover}
      className={cn(
        "flex h-full min-w-0 cursor-pointer flex-col justify-center rounded-full px-6 text-left transition-[background-color,box-shadow] duration-200",
        active ? "bg-white shadow-[0_3px_12px_rgb(0_0_0/0.1),0_1px_2px_rgb(0_0_0/0.08)]" : barActive ? "hover:bg-line" : "hover:bg-line-soft",
        className,
      )}
    >
      <span className="block text-xs font-medium">{label}</span>
      {children}
    </div>
  );
}

function Sep({ hidden }: { hidden?: boolean }) {
  return <span className={cn("h-8 w-px shrink-0 bg-line transition-opacity", hidden && "opacity-0")} />;
}

function AreaTile({ area, size = 56 }: { area?: Area; size?: number }) {
  const st = area ? areaStyle(area) : { icon: "globe" as Icon3DName, tint: "#eaf3fb" };
  return (
    <span className="grid shrink-0 place-items-center rounded-xl" style={{ width: size, height: size, background: st.tint }}>
      <Icon3D name={st.icon} size={Math.round(size * 0.62)} eager />
    </span>
  );
}

function WherePanel({ areas, selected, onPick, query }: { areas: Area[]; selected?: string; onPick: (slug?: string) => void; query: string }) {
  return (
    <div>
      <p className="px-4 pb-2 text-xs font-medium text-ink-2">{query ? "Neighbourhoods" : "Suggested destinations"}</p>
      <ul>
        {!query && (
          <AreaRow onClick={() => onPick(undefined)} selected={!selected} tile={<AreaTile />} title="Anywhere on the coast" subtitle="Every home from Mtwapa to Diani" />
        )}
        {areas.map((a) => (
          <AreaRow key={a.slug} onClick={() => onPick(a.slug)} selected={selected === a.slug} tile={<AreaTile area={a} />} title={`${a.name}, Mombasa`} subtitle={a.summary} />
        ))}
        {!areas.length && <li className="px-4 py-6 text-sm text-ink-2">No neighbourhood matches “{query}”. We host in Nyali, Diani, Old Town, Bamburi and Mtwapa.</li>}
      </ul>
    </div>
  );
}

function AreaRow({ onClick, selected, tile, title, subtitle }: { onClick: () => void; selected: boolean; tile: React.ReactNode; title: string; subtitle: string }) {
  return (
    <li>
      <button type="button" onClick={onClick} className={cn("flex w-full items-center gap-4 rounded-xl px-4 py-2 text-left transition-colors hover:bg-surface", selected && "bg-surface")}>
        {tile}
        <span className="min-w-0">
          <span className="block truncate text-base font-medium text-ink">{title}</span>
          <span className="line-clamp-1 text-sm text-ink-2">{subtitle}</span>
        </span>
      </button>
    </li>
  );
}

function DatesPanel({ s, onChange, months = 2 }: { s: SearchState; onChange: (r: { from?: string; to?: string }) => void; months?: 1 | 2 }) {
  return (
    <div>
      <RangeCalendar months={months} value={{ from: s.checkIn, to: s.checkOut }} onChange={onChange} />
      <div className="mt-6 flex flex-wrap items-center gap-2">
        {datePresets(s).map((p) => {
          const on = s.checkIn === iso(p.range[0]) && s.checkOut === iso(p.range[1]);
          return (
            <button
              key={p.label}
              type="button"
              onClick={() => onChange({ from: iso(p.range[0]), to: iso(p.range[1]) })}
              className={cn("h-[34px] rounded-3xl border px-3.5 text-xs transition-colors", on ? "border-ink" : "border-line hover:border-ink")}
            >
              {p.label}
            </button>
          );
        })}
        {s.checkIn && (
          <button type="button" onClick={() => onChange({})} className="ml-auto text-sm font-semibold underline underline-offset-2">
            Clear dates
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- compact pill (scrolled & inner pages)

export function CompactSearch({ onOpen, className }: { onOpen: (seg: Segment) => void; className?: string }) {
  const s = useSearchState();
  const { data: areas } = useAreas();
  const areaName = areas?.find((a) => a.slug === s.area)?.name;
  const who = s.adults + s.children;
  return (
    <div className={cn("flex h-12 items-center rounded-full border border-line-soft bg-white pr-2 pl-2 shadow-pill transition-shadow hover:shadow-card", className)}>
      <button type="button" onClick={() => onOpen("where")} className="flex h-full items-center gap-1.5 pr-4 pl-1 text-sm font-medium whitespace-nowrap">
        <Icon3D name="homes" size={34} eager />
        {areaName ? `Homes in ${areaName}` : "Anywhere"}
      </button>
      <span className="h-6 w-px bg-line" />
      <button type="button" onClick={() => onOpen("dates")} className="h-full px-4 text-sm font-medium whitespace-nowrap">
        {whenLabel(s, "Anytime")}
      </button>
      <span className="h-6 w-px bg-line" />
      <button type="button" onClick={() => onOpen("who")} className={cn("h-full pr-3 pl-4 text-sm whitespace-nowrap", who ? "font-medium" : "text-ink-2")}>
        {who ? guestsLabel(s) : "Add guests"}
      </button>
      <button type="button" onClick={() => onOpen("where")} aria-label="Search" className="grid size-8 place-items-center rounded-full bg-brand-600 text-white transition-colors hover:bg-brand-700">
        <Search className="size-3.5" strokeWidth={3.2} />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------- mobile

export function MobileSearch({ className }: { className?: string }) {
  const { s, setS, submit, areas, areaName } = useSearchDraft();
  const [open, setOpen] = React.useState(false);
  const [step, setStep] = React.useState<Segment>("where");
  const [query, setQuery] = React.useState("");
  const hasSearch = !!(areaName || s.checkIn || s.adults);
  const matches = areas.filter((a) => !query || `${a.name} ${a.summary}`.toLowerCase().includes(query.toLowerCase()));
  const go = () => {
    setOpen(false);
    submit();
  };
  return (
    <>
      <button
        type="button"
        onClick={() => {
          setStep("where");
          setOpen(true);
        }}
        className={cn("flex h-14 w-full items-center justify-center gap-3 rounded-full border border-line bg-white px-6 shadow-[0_6px_20px_rgb(0_0_0/0.1)]", className)}
      >
        <Search className="size-4 shrink-0" strokeWidth={2.8} />
        {hasSearch ? (
          <span className="min-w-0 text-left">
            <span className="block truncate text-sm font-medium">{areaName ? `Homes in ${areaName}` : "Homes anywhere"}</span>
            <span className="block truncate text-xs text-ink-2">{[whenLabel(s, "Any week"), guestsLabel(s)].join(" · ")}</span>
          </span>
        ) : (
          <span className="text-sm font-medium">Start your search</span>
        )}
      </button>
      <D.Root open={open} onOpenChange={setOpen}>
        <D.Portal>
          <D.Content className="fixed inset-0 z-50 flex flex-col bg-surface outline-none animate-fade-in" aria-describedby={undefined}>
            <D.Title className="sr-only">Search homes</D.Title>
            <div className="flex items-center justify-between px-5 pt-4 pb-2">
              <D.Close className="grid size-9 place-items-center rounded-full border border-line bg-white" aria-label="Close">
                <X className="size-4" strokeWidth={2.5} />
              </D.Close>
              <span className="flex items-center gap-1.5 text-sm font-semibold">
                <Icon3D name="homes" size={28} eager /> Homes
              </span>
              <span className="size-9" />
            </div>
            <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 pt-2 pb-6">
              <MobileStep open={step === "where"} title="Where to?" label="Where" value={areaName ?? "I'm flexible"} onOpen={() => setStep("where")}>
                <label className="flex h-14 items-center gap-3 rounded-xl border border-line px-4">
                  <Search className="size-4" strokeWidth={2.6} />
                  <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search destinations" className="w-full bg-transparent text-sm outline-none" />
                </label>
                <p className="mt-5 mb-2 text-xs font-medium text-ink-2">Suggested destinations</p>
                <ul className="-mx-4">
                  {!query && (
                    <AreaRow onClick={() => { setS({ ...s, area: undefined }); setStep("dates"); }} selected={!s.area} tile={<AreaTile />} title="Anywhere on the coast" subtitle="Every home from Mtwapa to Diani" />
                  )}
                  {matches.map((a) => (
                    <AreaRow key={a.slug} onClick={() => { setS({ ...s, area: a.slug }); setQuery(""); setStep("dates"); }} selected={s.area === a.slug} tile={<AreaTile area={a} />} title={`${a.name}, Mombasa`} subtitle={a.summary} />
                  ))}
                </ul>
              </MobileStep>
              <MobileStep open={step === "dates"} title="When's your trip?" label="When" value={whenLabel(s)} onOpen={() => setStep("dates")}>
                <DatesPanel s={s} months={1} onChange={(r) => { setS({ ...s, checkIn: r.from, checkOut: r.to }); if (r.from && r.to) setStep("who"); }} />
              </MobileStep>
              <MobileStep open={step === "who"} title="Who's coming?" label="Who" value={guestsLabel(s)} onOpen={() => setStep("who")}>
                <GuestPicker value={s} onChange={(g) => setS({ ...s, ...g })} max={6} />
              </MobileStep>
            </div>
            <div className="flex items-center justify-between border-t border-line-soft bg-white px-6 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
              <button type="button" className="text-base font-semibold underline underline-offset-2" onClick={() => { setS({ adults: 0, children: 0, infants: 0 }); setStep("where"); }}>
                Clear all
              </button>
              <Button variant="brand" size="lg" onClick={go} className="px-6">
                <Search className="size-4" strokeWidth={3} /> Search
              </Button>
            </div>
          </D.Content>
        </D.Portal>
      </D.Root>
    </>
  );
}

function MobileStep({ open, title, label, value, onOpen, children }: {
  open: boolean; title: string; label: string; value: string; onOpen: () => void; children: React.ReactNode;
}) {
  if (!open) {
    return (
      <button type="button" onClick={onOpen} className="flex w-full items-center justify-between rounded-2xl bg-white px-5 py-5 text-sm shadow-[0_2px_8px_rgb(0_0_0/0.06)]">
        <span className="text-ink-2">{label}</span>
        <span className="font-semibold">{value}</span>
      </button>
    );
  }
  return (
    <section className="rounded-[24px] bg-white p-5 shadow-[0_4px_20px_rgb(0_0_0/0.1)] animate-fade-in">
      <h2 className="mb-5 text-[26px] leading-tight font-semibold tracking-tight">{title}</h2>
      {children}
    </section>
  );
}

export function BackButton({ onClick, className }: { onClick: () => void; className?: string }) {
  return (
    <button type="button" onClick={onClick} aria-label="Back" className={cn("grid size-9 place-items-center rounded-full bg-white shadow-pill", className)}>
      <ChevronLeft className="size-4" strokeWidth={2.6} />
    </button>
  );
}
