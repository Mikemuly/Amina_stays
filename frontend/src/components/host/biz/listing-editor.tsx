"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Banknote, CalendarSync, Camera, ExternalLink, FileText, KeyRound, MoreHorizontal, ShieldCheck, Sparkles, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { ErrorBlock, PageHeader } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { Dropdown, DropdownContent, DropdownItem, DropdownTrigger, Tooltip } from "@/components/ui/overlays";
import { ApiError, del, get, patch, post } from "@/lib/api";
import { cn } from "@/lib/utils";

import { blankForm, changedKeys, sectionOf, toForm, toPayload, type FormKey, type ListingForm, type SetField } from "./listing-form";
import { CalendarSyncSection, PhotosSection } from "./listing-media";
import { AccessSection, AmenitiesSection, DetailsSection, PricingSection, RulesSection } from "./listing-sections";
import { HousekeepingChip, StatusChip } from "./listings";
import { useAreas, useInvalidateHost } from "./queries";
import type { HostListing } from "./types";
import { ConfirmDialog, SaveBar, errorMessage, fieldErrors, useTabParam, useUnsavedChanges } from "./ui";

const SECTIONS = [
  { key: "details", label: "Details", icon: FileText },
  { key: "photos", label: "Photos", icon: Camera },
  { key: "pricing", label: "Pricing", icon: Banknote },
  { key: "amenities", label: "Amenities", icon: Sparkles },
  { key: "rules", label: "Rules & safety", icon: ShieldCheck },
  { key: "access", label: "Access & arrival", icon: KeyRound },
  { key: "calendar", label: "Calendar sync", icon: CalendarSync },
] as const;
type SectionKey = (typeof SECTIONS)[number]["key"];
const SECTION_KEYS = SECTIONS.map((s) => s.key);

export function ListingEditor({ id }: { id: string }) {
  const isNew = id === "new";
  const valid = isNew || /^\d+$/.test(id);
  const areasQ = useAreas();
  const listingQ = useQuery({
    queryKey: ["host", "listing", id],
    queryFn: () => get<HostListing>(`/api/host/listings/${id}`),
    enabled: valid && !isNew,
  });

  if (!valid || (listingQ.error instanceof ApiError && listingQ.error.status === 404)) {
    return (
      <EmptyState
        title="We couldn't find that listing"
        action={
          <Button asChild variant="dark">
            <Link href="/host/listings">Back to listings</Link>
          </Button>
        }
      >
        It may have been deleted. Your other homes are on the listings page.
      </EmptyState>
    );
  }
  if (listingQ.error || areasQ.error) return <ErrorBlock error={listingQ.error ?? areasQ.error} retry={() => (listingQ.error ? listingQ.refetch() : areasQ.refetch())} />;
  const listing = isNew ? null : listingQ.data;
  if (listing === undefined || !areasQ.data) return <EditorSkeleton />;

  return <EditorForm key={id} listing={listing} defaultArea={areasQ.data[0]?.slug ?? ""} />;
}

function EditorSkeleton() {
  return (
    <div>
      <Skeleton className="mb-3 h-4 w-24" />
      <Skeleton className="mb-8 h-8 w-72" />
      <div className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
        <div className="space-y-2">
          {Array.from({ length: 7 }).map((_, i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
        <Skeleton className="h-[520px] rounded-2xl" />
      </div>
    </div>
  );
}

function EditorForm({ listing, defaultArea }: { listing: HostListing | null; defaultArea: string }) {
  const isNew = listing === null;
  const router = useRouter();
  const qc = useQueryClient();
  const invalidate = useInvalidateHost();
  const [section, setSection] = useTabParam<SectionKey>(SECTION_KEYS, "details", "section");

  const base = React.useMemo(() => (listing ? toForm(listing) : blankForm(defaultArea)), [listing, defaultArea]);
  const [draft, setDraft] = React.useState<ListingForm>(base);
  const [seenBase, setSeenBase] = React.useState(base);
  if (seenBase !== base) {
    // Server copy changed (refetch, photo edits…): adopt it unless there are unsaved edits.
    setSeenBase(base);
    if (changedKeys(seenBase, draft).length === 0) setDraft(base);
  }
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [saving, setSaving] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);

  const changed = isNew ? [] : changedKeys(base, draft);

  const set: SetField = React.useCallback((key, value) => {
    setDraft((d) => ({ ...d, [key]: value }));
    setErrors((e) => {
      if (!(key in e)) return e;
      const next = { ...e };
      delete next[key];
      return next;
    });
  }, []);

  const handleError = (e: unknown) => {
    const fe = fieldErrors(e);
    setErrors(fe);
    const first = Object.keys(fe).map(sectionOf).find(Boolean);
    if (first && first !== section) setSection(first);
    toast.error(errorMessage(e, "Couldn't save the listing."));
  };

  const save = async () => {
    if (saving) return;
    setSaving(true);
    try {
      const payload = toPayload(draft);
      if (isNew) {
        const created = await post<HostListing>("/api/host/listings", payload);
        qc.setQueryData(["host", "listing", String(created.id)], created);
        invalidate();
        toast.success(`${created.name} created`, { description: "Now add photos — the first one becomes the cover." });
        router.replace(`/host/listings/${created.id}?section=photos`);
        return;
      }
      if (!changed.length) return;
      const body = Object.fromEntries(changed.map((k) => [k, payload[k]]));
      const updated = await patch<HostListing>(`/api/host/listings/${listing.id}`, body);
      qc.setQueryData(["host", "listing", String(listing.id)], updated);
      setDraft(toForm(updated));
      setErrors({});
      invalidate();
      toast.success("Listing saved", { description: "Live on the website, USSD and SMS straight away." });
    } catch (e) {
      handleError(e);
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!listing) return;
    setDeleting(true);
    try {
      const r = await del<{ paused?: boolean; detail?: string } | undefined>(`/api/host/listings/${listing.id}`);
      invalidate();
      if (r?.paused) toast.message(`${listing.name} was paused instead`, { description: r.detail });
      else toast.success(`${listing.name} deleted`);
      router.push("/host/listings");
    } catch (e) {
      toast.error(errorMessage(e));
      setDeleting(false);
    }
  };

  const errorSections = new Set(Object.keys(errors).map(sectionOf).filter(Boolean));
  const dirtySections = new Set(changed.map((k) => sectionOf(k)).filter(Boolean));
  const sectionProps = { draft, set, errors };

  return (
    <>
      <PageHeader
        back={{ href: "/host/listings", label: "Listings" }}
        title={draft.name.trim() || (isNew ? "New listing" : "Untitled home")}
        subtitle={
          listing ? (
            <span className="flex flex-wrap items-center gap-2">
              <StatusChip status={listing.status} className="border border-line-soft shadow-none" />
              <HousekeepingChip value={listing.housekeeping} />
              <span className="text-[13px]">/{listing.slug}</span>
            </span>
          ) : (
            "Start with the basics and a price — you can add photos once it's created. New homes start as drafts."
          )
        }
        actions={
          listing && (
            <>
              {listing.status === "active" ? (
                <Button asChild variant="soft">
                  <a href={`/stays/${listing.slug}`} target="_blank" rel="noreferrer">
                    <ExternalLink className="size-4" /> View on site
                  </a>
                </Button>
              ) : (
                <Tooltip content="Only listed homes are public. Set the status to Listed to publish.">
                  <span>
                    <Button variant="soft" disabled>
                      <ExternalLink className="size-4" /> View on site
                    </Button>
                  </span>
                </Tooltip>
              )}
              <Dropdown>
                <DropdownTrigger asChild>
                  <Button variant="soft" size="icon" aria-label="More listing actions" className="size-10 rounded-lg">
                    <MoreHorizontal className="size-4" />
                  </Button>
                </DropdownTrigger>
                <DropdownContent>
                  <DropdownItem className="text-danger" onSelect={() => setConfirmDelete(true)}>
                    <Trash2 className="size-4" /> Delete listing
                  </DropdownItem>
                </DropdownContent>
              </Dropdown>
            </>
          )
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
        <nav aria-label="Listing sections" className="min-w-0 lg:sticky lg:top-6 lg:self-start">
          <ul className="no-scrollbar -mx-4 flex gap-1 overflow-x-auto px-4 pb-1 lg:mx-0 lg:flex-col lg:px-0">
            {SECTIONS.map((s) => {
              const active = s.key === section;
              const needsSave = isNew && (s.key === "photos" || s.key === "calendar");
              return (
                <li key={s.key} className="shrink-0">
                  <button
                    type="button"
                    onClick={() => setSection(s.key)}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-[14px] font-medium whitespace-nowrap transition-colors",
                      active ? "bg-white font-semibold text-ink shadow-soft ring-1 ring-line-soft" : "text-ink-2 hover:bg-white/70 hover:text-ink",
                    )}
                  >
                    <s.icon className="size-[18px] shrink-0" />
                    <span className="flex-1">{s.label}</span>
                    {errorSections.has(s.key) ? (
                      <span className="size-2 rounded-full bg-danger" aria-label="has errors" />
                    ) : dirtySections.has(s.key) ? (
                      <span className="size-2 rounded-full bg-brand-500" aria-label="unsaved changes" />
                    ) : needsSave ? (
                      <span className="text-[11px] font-semibold text-ink-3">after saving</span>
                    ) : s.key === "photos" && listing ? (
                      <span className="text-[12px] text-ink-3 tabular-nums">{listing.photos.length}</span>
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="min-w-0 space-y-6">
          {section === "details" && <DetailsSection {...sectionProps} />}
          {section === "pricing" && <PricingSection {...sectionProps} />}
          {section === "amenities" && <AmenitiesSection {...sectionProps} />}
          {section === "rules" && <RulesSection {...sectionProps} />}
          {section === "access" && <AccessSection {...sectionProps} />}
          {(section === "photos" || section === "calendar") &&
            (listing ? (
              section === "photos" ? (
                <PhotosSection listing={listing} />
              ) : (
                <CalendarSyncSection listing={listing} />
              )
            ) : (
              <EmptyState
                icon={section === "photos" ? <Camera className="size-5" /> : <CalendarSync className="size-5" />}
                title={section === "photos" ? "Create the listing to add photos" : "Create the listing to sync calendars"}
                action={
                  <Button variant="dark" onClick={save} loading={saving}>
                    Create listing
                  </Button>
                }
              >
                Fill in the name, area and base price first — everything else can be added later.
              </EmptyState>
            ))}
        </div>
      </div>

      {isNew ? (
        <NewListingBar saving={saving} onSave={save} onDiscard={() => router.push("/host/listings")} draft={draft} />
      ) : (
        <SaveBar
          count={changed.length}
          saving={saving}
          onSave={save}
          onDiscard={() => {
            setDraft(base);
            setErrors({});
          }}
        />
      )}

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete ${listing?.name ?? "listing"}?`}
        confirmLabel="Delete listing"
        tone="danger"
        loading={deleting}
        onConfirm={remove}
      >
        <p>It disappears from the website, USSD and SMS menus straight away.</p>
        <p>Homes with booking history are <b className="text-ink">paused</b> instead of deleted, so past stays, payments and the guest register stay intact.</p>
      </ConfirmDialog>
    </>
  );
}

function NewListingBar({ saving, onSave, onDiscard, draft }: { saving: boolean; onSave: () => void; onDiscard: () => void; draft: ListingForm }) {
  const required: [FormKey, string][] = [
    ["name", "name"],
    ["area", "area"],
    ["base_price", "base price"],
  ];
  const missing = required.filter(([k]) => draft[k] === null || String(draft[k]).trim() === "").map(([, label]) => label);
  useUnsavedChanges(draft.name.trim() !== "" || draft.base_price !== null, onSave);
  return (
    <div className="pointer-events-none sticky bottom-4 z-30 mt-6 flex justify-center">
      <div className="pointer-events-auto flex w-full max-w-2xl items-center gap-2 rounded-2xl bg-ink py-2.5 pr-2.5 pl-5 text-white shadow-float animate-slide-up">
        <p className="min-w-0 flex-1 truncate text-sm">
          <span className="font-semibold">New listing</span>
          <span className="ml-2 text-white/60">{missing.length ? `Add a ${missing.join(" and ")} to create it` : "Ready to create as a draft"}</span>
        </p>
        <Button variant="ghost" size="sm" className="text-white hover:bg-white/10" onClick={onDiscard} disabled={saving}>
          Cancel
        </Button>
        <Button variant="brand" size="sm" onClick={onSave} loading={saving}>
          Create listing
        </Button>
      </div>
    </div>
  );
}

