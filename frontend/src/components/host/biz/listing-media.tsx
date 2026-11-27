"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarSync, ChevronLeft, ChevronRight, ImagePlus, Link2, RefreshCw, Star, Trash2, Upload } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { useConfig } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { Switch } from "@/components/ui/overlays";
import { del, get, patch, post } from "@/lib/api";
import { plural } from "@/lib/format";
import { sized } from "@/lib/img";
import { cn } from "@/lib/utils";

import { PHOTO_ROOMS } from "./listing-form";
import { useInvalidateHost } from "./queries";
import type { HostListing, HostPhoto, ICalFeed } from "./types";
import { Callout, ConfirmDialog, CopyField, Field, FormCard, IconButton, Segmented, errorMessage, fieldErrors, humanize, since } from "./ui";

// ---------- Photos ----------

export function PhotosSection({ listing }: { listing: HostListing }) {
  const qc = useQueryClient();
  const invalidate = useInvalidateHost();
  const [order, setOrder] = React.useState<number[] | null>(null);
  const [adding, setAdding] = React.useState(false);
  const [toDelete, setToDelete] = React.useState<HostPhoto | null>(null);
  const [deleting, setDeleting] = React.useState(false);
  const seq = React.useRef(0);

  const byId = new Map(listing.photos.map((p) => [p.id, p]));
  const photos = order ? order.map((id) => byId.get(id)).filter((p): p is HostPhoto => !!p) : listing.photos;

  const setPhotos = (next: HostPhoto[]) =>
    qc.setQueryData<HostListing>(["host", "listing", String(listing.id)], (old) => (old ? { ...old, photos: next } : old));

  const saveOrder = async (ids: number[]) => {
    const mine = ++seq.current;
    setOrder(ids);
    try {
      setPhotos(await post<HostPhoto[]>(`/api/host/listings/${listing.id}/photos/order`, { ids }));
      invalidate();
    } catch (e) {
      toast.error(errorMessage(e, "Couldn't reorder the photos."));
    } finally {
      if (mine === seq.current) setOrder(null);
    }
  };

  const move = (from: number, to: number) => {
    const ids = photos.map((p) => p.id);
    const [id] = ids.splice(from, 1);
    ids.splice(to, 0, id);
    saveOrder(ids);
  };

  const remove = async () => {
    if (!toDelete) return;
    setDeleting(true);
    try {
      await del(`/api/host/listings/${listing.id}/photos/${toDelete.id}`);
      setPhotos(listing.photos.filter((p) => p.id !== toDelete.id));
      invalidate();
      toast.success("Photo removed");
      setToDelete(null);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <FormCard
      title="Photos"
      description={`${plural(photos.length, "photo")} · the first one is the cover on cards, search results and shared links.`}
      action={
        <Button variant="dark" size="sm" onClick={() => setAdding(true)}>
          <ImagePlus className="size-4" /> Add photo
        </Button>
      }
    >
      {photos.length === 0 ? (
        <EmptyState
          icon={<ImagePlus className="size-5" />}
          title="Add your first photo"
          action={
            <Button variant="dark" onClick={() => setAdding(true)}>
              <Upload className="size-4" /> Upload or link a photo
            </Button>
          }
        >
          Lead with the view or the living room. Landscape photos at least 1600px wide look best.
        </EmptyState>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {photos.map((p, i) => (
            <li key={p.id} className="group overflow-hidden rounded-xl border border-line-soft bg-white">
              <div className="relative aspect-[4/3] bg-surface">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={sized(p.src, 640)} alt={p.caption || `Photo ${i + 1}`} loading="lazy" className="size-full object-cover" />
                {i === 0 && (
                  <span className="absolute top-2.5 left-2.5 inline-flex items-center gap-1 rounded-full bg-white px-2.5 py-1 text-[11.5px] font-bold shadow-sm">
                    <Star className="size-3 fill-brand-500 text-brand-500" /> Cover photo
                  </span>
                )}
                <span className="absolute bottom-2.5 left-2.5 rounded-full bg-black/55 px-2 py-0.5 text-[11.5px] font-semibold text-white tabular-nums backdrop-blur">
                  {i + 1}
                </span>
                <div className="absolute top-2.5 right-2.5 flex gap-1 transition sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100">
                  <PhotoAction label="Move earlier" disabled={i === 0} onClick={() => move(i, i - 1)}>
                    <ChevronLeft />
                  </PhotoAction>
                  <PhotoAction label="Move later" disabled={i === photos.length - 1} onClick={() => move(i, i + 1)}>
                    <ChevronRight />
                  </PhotoAction>
                  {i > 0 && (
                    <PhotoAction label="Make cover photo" onClick={() => move(i, 0)}>
                      <Star />
                    </PhotoAction>
                  )}
                  <PhotoAction label="Delete photo" danger onClick={() => setToDelete(p)}>
                    <Trash2 />
                  </PhotoAction>
                </div>
              </div>
              <div className="flex items-center justify-between gap-3 px-3.5 py-2.5">
                <p className={cn("min-w-0 truncate text-[13px] font-medium", !p.caption && "text-ink-3")}>{p.caption || "No caption"}</p>
                <span className="shrink-0 rounded-full bg-surface px-2 py-0.5 text-[11.5px] font-semibold text-ink-2">{humanize(p.room)}</span>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Dialog open={adding} onOpenChange={setAdding}>
        {adding && (
          <AddPhotoContent
            listingId={listing.id}
            onAdded={(photo) => {
              setPhotos([...listing.photos, photo]);
              invalidate();
              setAdding(false);
            }}
          />
        )}
      </Dialog>

      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(v) => !v && setToDelete(null)}
        title="Delete this photo?"
        confirmLabel="Delete photo"
        tone="danger"
        loading={deleting}
        onConfirm={remove}
      >
        {toDelete && (
          <div className="flex items-center gap-4">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={sized(toDelete.src, 240)} alt="" className="h-16 w-24 shrink-0 rounded-lg object-cover" />
            <p>It disappears from the listing everywhere straight away. This can&apos;t be undone.</p>
          </div>
        )}
      </ConfirmDialog>
    </FormCard>
  );
}

function PhotoAction({ label, danger, children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string; danger?: boolean }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cn(
        "grid size-8 place-items-center rounded-full bg-white/95 text-ink shadow-sm transition hover:bg-white disabled:pointer-events-none disabled:opacity-40 [&_svg]:size-4",
        danger && "hover:text-danger",
      )}
      {...props}
    >
      {children}
    </button>
  );
}

function AddPhotoContent({ listingId, onAdded }: { listingId: number; onAdded: (p: HostPhoto) => void }) {
  const [mode, setMode] = React.useState<"upload" | "url">("upload");
  const [file, setFile] = React.useState<File | null>(null);
  const [preview, setPreview] = React.useState<string | null>(null);
  const [url, setUrl] = React.useState("");
  const [caption, setCaption] = React.useState("");
  const [room, setRoom] = React.useState("living");
  const [saving, setSaving] = React.useState(false);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [dragOver, setDragOver] = React.useState(false);

  React.useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  const pick = (f: File | undefined | null) => {
    if (!f) return;
    if (!f.type.startsWith("image/")) {
      toast.error("That isn't an image file.");
      return;
    }
    setFile(f);
    setPreview(URL.createObjectURL(f));
  };

  const ready = mode === "upload" ? !!file : /^https?:\/\/\S+$/.test(url.trim());

  const submit = async () => {
    setSaving(true);
    setErrors({});
    try {
      let photo: HostPhoto;
      if (mode === "upload" && file) {
        const fd = new FormData();
        fd.append("image", file);
        fd.append("caption", caption.trim());
        fd.append("room", room);
        photo = await post<HostPhoto>(`/api/host/listings/${listingId}/photos`, fd);
      } else {
        photo = await post<HostPhoto>(`/api/host/listings/${listingId}/photos`, { url: url.trim(), caption: caption.trim(), room });
      }
      toast.success("Photo added");
      onAdded(photo);
    } catch (e) {
      setErrors(fieldErrors(e));
      toast.error(errorMessage(e, "Couldn't add the photo."));
    } finally {
      setSaving(false);
    }
  };

  const shownPreview = mode === "upload" ? preview : ready ? url.trim() : null;

  return (
    <DialogContent
      title="Add a photo"
      size="md"
      footer={
        <div className="flex items-center justify-between gap-3">
          <p className="text-[12.5px] text-ink-2">New photos go to the end — reorder them after.</p>
          <Button variant="dark" onClick={submit} loading={saving} disabled={!ready}>
            Add photo
          </Button>
        </div>
      }
    >
      <div className="space-y-5 px-6 py-5">
        <Segmented<"upload" | "url">
          label="Photo source"
          value={mode}
          onChange={setMode}
          options={[
            { value: "upload", label: "Upload a file" },
            { value: "url", label: "From a link" },
          ]}
        />
        {mode === "upload" ? (
          <label
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              pick(e.dataTransfer.files?.[0]);
            }}
            className={cn(
              "relative flex aspect-[16/9] cursor-pointer flex-col items-center justify-center gap-2 overflow-hidden rounded-xl border-2 border-dashed text-center transition",
              dragOver ? "border-ink bg-surface" : "border-line hover:border-ink-3",
            )}
          >
            {preview ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={preview} alt="Selected photo preview" className="absolute inset-0 size-full object-cover" />
            ) : (
              <>
                <Upload className="size-6 text-ink-2" />
                <span className="text-[15px] font-semibold">Drop a photo here or click to browse</span>
                <span className="text-[13px] text-ink-2">JPG, PNG or WebP</span>
              </>
            )}
            <input type="file" accept="image/*" className="sr-only" onChange={(e) => pick(e.target.files?.[0])} />
          </label>
        ) : (
          <>
            <Field label="Image URL" error={errors.url} hint="A direct link to a JPG/PNG (e.g. from Unsplash or your own site).">
              <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://images.unsplash.com/photo-…" />
            </Field>
            {shownPreview && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={sized(shownPreview, 960)} alt="Linked photo preview" className="aspect-[16/9] w-full rounded-xl bg-surface object-cover" />
            )}
          </>
        )}
        {errors.image && <p className="text-[13px] text-danger">{errors.image}</p>}
        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_180px]">
          <Field label="Caption" error={errors.caption} hint="Helps guests (and screen readers) know what they're looking at.">
            <Input value={caption} maxLength={120} onChange={(e) => setCaption(e.target.value)} placeholder="Ocean view from the balcony" />
          </Field>
          <Field label="Room" error={errors.room}>
            <Select value={room} onChange={(e) => setRoom(e.target.value)}>
              {PHOTO_ROOMS.map((r) => (
                <option key={r} value={r}>
                  {humanize(r)}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </div>
    </DialogContent>
  );
}

// ---------- Calendar sync (iCal) ----------

const FEED_SOURCES = ["Airbnb", "Booking.com", "Vrbo", "Google Calendar", "Other"];
const FEED_COLORS: Record<string, string> = { airbnb: "#ff385c", "booking.com": "#1e40af", vrbo: "#1d4ed8", "google calendar": "#0e8388" };

export function CalendarSyncSection({ listing }: { listing: HostListing }) {
  const { data: config } = useConfig();
  const invalidate = useInvalidateHost();
  const feedsQ = useQuery({ queryKey: ["host", "ical-feeds"], queryFn: () => get<ICalFeed[]>("/api/host/ical-feeds") });
  const feeds = (feedsQ.data ?? []).filter((f) => f.unit === listing.id);
  const [name, setName] = React.useState("Airbnb");
  const [url, setUrl] = React.useState("");
  const [adding, setAdding] = React.useState(false);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState<number | null>(null);
  const [toDelete, setToDelete] = React.useState<ICalFeed | null>(null);
  const [deleting, setDeleting] = React.useState(false);

  const add = async () => {
    setAdding(true);
    setError("");
    try {
      const feed = await post<ICalFeed>("/api/host/ical-feeds", { unit: listing.id, name, url: url.trim(), active: true });
      setUrl("");
      toast.success(`${feed.name} calendar connected — syncing now…`);
      await sync(feed, true);
    } catch (e) {
      setError(fieldErrors(e).url || errorMessage(e));
    } finally {
      setAdding(false);
      invalidate();
    }
  };

  const sync = async (feed: ICalFeed, quiet = false) => {
    setBusy(feed.id);
    try {
      const r = await post<{ ok: boolean; events?: number; conflicts?: number; error?: string }>(`/api/host/ical-feeds/${feed.id}/sync`);
      if (r.ok) {
        if (r.conflicts) toast.warning(`${plural(r.conflicts, "clash", "clashes")} with direct bookings — check Safety alerts.`);
        else if (!quiet || r.events) toast.success(`${feed.name}: ${plural(r.events ?? 0, "booking")} imported`);
      } else toast.error(`${feed.name} sync failed: ${r.error ?? "unknown error"}`);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(null);
      invalidate();
    }
  };

  const toggle = async (feed: ICalFeed, active: boolean) => {
    try {
      await patch(`/api/host/ical-feeds/${feed.id}`, { active });
      invalidate();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  const remove = async () => {
    if (!toDelete) return;
    setDeleting(true);
    try {
      await del(`/api/host/ical-feeds/${toDelete.id}`);
      toast.success(`${toDelete.name} calendar disconnected`);
      setToDelete(null);
      invalidate();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <>
      <FormCard title="Export this calendar" description="Keep Airbnb and Booking.com in step with bookings made here — on the web, by USSD, SMS or voice.">
        <CopyField value={listing.ical_export_url} label="Copy iCal link" />
        <ol className="grid gap-3 text-[13.5px] text-ink-2 sm:grid-cols-3">
          {[
            "Copy the link above.",
            "In Airbnb or Booking.com open the calendar's availability settings → “Import calendar”.",
            "Paste the link and name it “Amina Stays”. They re-check it every few hours.",
          ].map((t, i) => (
            <li key={i} className="flex gap-2.5 rounded-xl bg-surface px-3.5 py-3">
              <span className="grid size-5 shrink-0 place-items-center rounded-full bg-ink text-[11px] font-bold text-white">{i + 1}</span>
              {t}
            </li>
          ))}
        </ol>
      </FormCard>

      <FormCard
        title="Import calendars"
        description="Nights sold on other sites are blocked here automatically, so they can't be double-booked through any channel."
      >
        {feedsQ.isLoading ? (
          <Skeleton className="h-20" />
        ) : feeds.length === 0 ? (
          <div className="flex items-center gap-3 rounded-xl border border-dashed border-line px-4 py-5 text-[14px] text-ink-2">
            <CalendarSync className="size-5 shrink-0" /> No calendars imported yet. Add your Airbnb or Booking.com export link below.
          </div>
        ) : (
          <ul className="divide-y divide-line-soft rounded-xl border border-line-soft">
            {feeds.map((f) => (
              <li key={f.id} className="flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3.5">
                <span
                  className="grid size-10 shrink-0 place-items-center rounded-xl text-[15px] font-bold text-white"
                  style={{ background: FEED_COLORS[f.name.toLowerCase()] ?? "#222" }}
                  aria-hidden
                >
                  {f.name.charAt(0).toUpperCase()}
                </span>
                <div className="min-w-0 flex-1 basis-56">
                  <p className="text-[15px] font-semibold">{f.name}</p>
                  <p className="truncate font-mono text-[12px] text-ink-2" title={f.url}>
                    {f.url}
                  </p>
                  <p className={cn("mt-1 text-[12.5px] font-medium", !f.last_synced_at ? "text-ink-2" : f.last_ok ? "text-success" : "text-danger")}>
                    {!f.last_synced_at
                      ? "Not synced yet"
                      : f.last_ok
                        ? `✓ Synced ${since(f.last_synced_at)} · ${plural(f.events_count, "upcoming booking")}`
                        : `✕ Last sync failed ${since(f.last_synced_at)}: ${f.last_error}`}
                  </p>
                </div>
                <label className="flex items-center gap-2 text-[13px] font-medium text-ink-2">
                  <Switch checked={f.active} onCheckedChange={(v) => toggle(f, v)} aria-label={`Auto-sync ${f.name}`} />
                  Auto-sync
                </label>
                <Button variant="soft" size="sm" loading={busy === f.id} onClick={() => sync(f)}>
                  {busy !== f.id && <RefreshCw className="size-3.5" />} Sync now
                </Button>
                <IconButton label={`Remove ${f.name} calendar`} tone="danger" onClick={() => setToDelete(f)}>
                  <Trash2 />
                </IconButton>
              </li>
            ))}
          </ul>
        )}

        <div className="rounded-xl bg-surface p-4">
          <p className="mb-3 text-[14px] font-semibold">Add a calendar</p>
          <div className="grid gap-3 sm:grid-cols-[180px_minmax(0,1fr)_auto]">
            <Select value={name} onChange={(e) => setName(e.target.value)} aria-label="Calendar source" className="bg-white">
              {FEED_SOURCES.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </Select>
            <div className="relative">
              <Link2 className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-ink-3" />
              <Input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.airbnb.com/calendar/ical/….ics"
                aria-label="Calendar export link (.ics)"
                className="bg-white pl-10"
              />
            </div>
            <Button variant="dark" className="h-11" onClick={add} loading={adding} disabled={!/^https?:\/\/\S+$/.test(url.trim())}>
              Connect
            </Button>
          </div>
          {error && <p className="mt-2 text-[13px] text-danger">{error}</p>}
          {config?.demo && (
            <button
              type="button"
              className="mt-2.5 text-[13px] font-semibold text-ocean-700 underline underline-offset-2"
              onClick={() => {
                setName("Airbnb");
                setUrl(`${window.location.origin}/api/demo/ical/${listing.slug}.ics`);
              }}
            >
              Demo: use a sample Airbnb calendar
            </button>
          )}
        </div>

        <Callout tone="info">
          Imported nights show as “Booked elsewhere” on the multi-calendar and are re-checked every 15 minutes. If one overlaps a direct booking, a
          critical alert fires so you can fix it before anyone arrives.
        </Callout>
      </FormCard>

      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(v) => !v && setToDelete(null)}
        title={`Disconnect ${toDelete?.name ?? "calendar"}?`}
        confirmLabel="Disconnect"
        tone="danger"
        loading={deleting}
        onConfirm={remove}
      >
        Nights imported from this calendar will be released, so they become bookable here again.
      </ConfirmDialog>
    </>
  );
}
