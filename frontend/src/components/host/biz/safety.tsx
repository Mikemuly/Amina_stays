"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { BadgeCheck, CalendarX2, Check, CircleCheck, MessageSquareWarning, Phone, ShieldAlert, Siren, Star, Wallet, Wrench, type LucideIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { ChannelBadge, ErrorBlock, LoadingBlock, PageHeader } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Badge, EmptyState } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/overlays";
import { get, post } from "@/lib/api";
import { ago, fmtDateTime, plural } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useInvalidateHost } from "./queries";
import { ChecklistTab, RegisterTab, TraReturnTab } from "./safety-compliance";
import type { AlertItem } from "./types";
import { Callout, ConfirmDialog, Field, Segmented, errorMessage, humanize, reservationHref, useTabParam } from "./ui";

const TABS = ["alerts", "register", "tra", "checklist"] as const;

export function SafetyPage() {
  const [tab, setTab] = useTabParam(TABS, "alerts");
  const { data: active } = useQuery({ queryKey: ["host", "alerts", "active"], queryFn: () => get<AlertItem[]>("/api/host/alerts?status=active"), refetchInterval: 10_000 });
  const open = active?.filter((a) => a.status === "open").length ?? 0;
  return (
    <>
      <PageHeader
        title="Safety & compliance"
        subtitle="Guest emergencies first — then the guest register, TRA return and the legal checklist that keep Amina Stays licensed."
      />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="no-scrollbar mb-6 overflow-x-auto">
          <TabsTrigger value="alerts" className="flex shrink-0 items-center gap-2">
            Alerts
            {open > 0 && <span className="min-w-5 rounded-full bg-danger px-1.5 text-center text-[11px] leading-5 font-bold text-white">{open}</span>}
          </TabsTrigger>
          <TabsTrigger value="register" className="shrink-0">Guest register</TabsTrigger>
          <TabsTrigger value="tra" className="shrink-0">TRA monthly return</TabsTrigger>
          <TabsTrigger value="checklist" className="shrink-0">Compliance checklist</TabsTrigger>
        </TabsList>
        <TabsContent value="alerts" className="outline-none">
          <AlertsTab />
        </TabsContent>
        <TabsContent value="register" className="outline-none">
          <RegisterTab />
        </TabsContent>
        <TabsContent value="tra" className="outline-none">
          <TraReturnTab />
        </TabsContent>
        <TabsContent value="checklist" className="outline-none">
          <ChecklistTab />
        </TabsContent>
      </Tabs>
    </>
  );
}

// ---------- alerts ----------

type StatusFilter = "active" | "resolved" | "all";

const KIND_ICON: Record<string, LucideIcon> = { sos: Siren, urgent_issue: Wrench, low_review: Star, conflict: CalendarX2, security: ShieldAlert, payment: Wallet, compliance: BadgeCheck, sms: MessageSquareWarning };
const SEVERITY: Record<AlertItem["severity"], { stripe: string; icon: string; badge: "danger" | "brand" | "warning" | "neutral" }> = {
  critical: { stripe: "bg-danger", icon: "bg-danger text-white", badge: "danger" },
  high: { stripe: "bg-brand-500", icon: "bg-brand-50 text-brand-600", badge: "brand" },
  medium: { stripe: "bg-warning", icon: "bg-warning-50 text-warning", badge: "warning" },
  low: { stripe: "bg-line", icon: "bg-surface text-ink-2", badge: "neutral" },
};
const SEVERITY_RANK = { critical: 0, high: 1, medium: 2, low: 3 };
const STATUS_RANK = { open: 0, acknowledged: 1, resolved: 2 };

function callText(a: AlertItem) {
  if (!a.calls_made && !a.call_status) return null;
  const status = a.call_status === "dry_run" ? "simulated (no voice number in sandbox)" : humanize(a.call_status.toLowerCase());
  return `${plural(a.calls_made, "call")} placed${status ? ` · ${status}` : ""}`;
}

function AlertsTab() {
  const invalidate = useInvalidateHost();
  const [status, setStatus] = React.useState<StatusFilter>("active");
  const [resolving, setResolving] = React.useState<AlertItem | null>(null);
  const [note, setNote] = React.useState("");
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["host", "alerts", status],
    queryFn: () => get<AlertItem[]>(`/api/host/alerts?status=${status}`),
    refetchInterval: 10_000,
  });

  const ack = useMutation({
    mutationFn: (a: AlertItem) => post<AlertItem>(`/api/host/alerts/${a.id}/ack`),
    onSuccess: () => {
      toast.success("Acknowledged — follow-up calls stopped");
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const resolve = useMutation({
    mutationFn: ({ a, note }: { a: AlertItem; note: string }) => post<AlertItem>(`/api/host/alerts/${a.id}/resolve`, { note }),
    onSuccess: () => {
      toast.success("Alert resolved");
      setResolving(null);
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const alerts = [...(data ?? [])].sort(
    (a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status] || SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] || b.id - a.id,
  );

  return (
    <div className="space-y-5">
      <Callout tone="trust" title="How an SOS reaches you">
        A guest replying HELP or MSAADA by SMS, pressing 9 on a call or in the USSD menu, or tapping SOS on the website skips every queue: your phone rings
        through Africa&apos;s Talking Voice and you get an SMS with who and where. If nobody acknowledges within 3 minutes, the backup contact is called.
      </Callout>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented<StatusFilter>
          label="Alert status"
          value={status}
          onChange={setStatus}
          options={[
            { value: "active", label: "Active" },
            { value: "resolved", label: "Resolved" },
            { value: "all", label: "All" },
          ]}
        />
        {data && <p className="text-[13px] text-ink-2">{plural(data.length, "alert")}</p>}
      </div>

      {error ? (
        <ErrorBlock error={error} retry={refetch} />
      ) : isLoading ? (
        <LoadingBlock rows={4} />
      ) : alerts.length === 0 ? (
        <EmptyState icon={<CircleCheck className="size-5" />} title={status === "active" ? "All clear" : "Nothing here"}>
          {status === "active" ? "No open alerts. SOS calls, urgent faults, low reviews and calendar clashes show up here the moment they happen." : "No alerts match this filter."}
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          {alerts.map((a) => {
            const Icon = KIND_ICON[a.kind] ?? ShieldAlert;
            const sev = SEVERITY[a.severity] ?? SEVERITY.low;
            const live = a.kind === "sos" && a.status === "open";
            const calls = callText(a);
            return (
              <li key={a.id} className={cn("relative overflow-hidden rounded-2xl border bg-white", live ? "border-danger/40 shadow-soft" : "border-line-soft", a.status === "resolved" && "opacity-80")}>
                <span className={cn("absolute inset-y-0 left-0 w-1", a.status === "resolved" ? "bg-line" : sev.stripe)} aria-hidden />
                <div className="flex flex-wrap gap-4 py-4 pr-5 pl-6">
                  <span className={cn("grid size-11 shrink-0 place-items-center rounded-full", a.status === "resolved" ? "bg-surface text-ink-3" : sev.icon, live && "animate-pulse-ring")}>
                    <Icon className="size-5" />
                  </span>
                  <div className="min-w-0 flex-1 basis-72">
                    <p className="flex flex-wrap items-center gap-2">
                      <span className="text-[15px] font-bold">{a.kind_label}</span>
                      <Badge tone={sev.badge}>{humanize(a.severity)}</Badge>
                      <Badge tone={a.status === "open" ? "danger" : a.status === "acknowledged" ? "ocean" : "neutral"} dot>
                        {humanize(a.status)}
                      </Badge>
                    </p>
                    <p className="mt-1 text-[14.5px] leading-relaxed text-ink">{a.summary}</p>
                    {a.details && <p className="mt-1.5 rounded-lg bg-surface px-3 py-2 text-[13.5px] text-ink-2 italic">“{a.details}”</p>}
                    <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] text-ink-2">
                      {a.source && ["sms", "voice", "web", "ussd", "whatsapp"].includes(a.source) ? <ChannelBadge channel={a.source} /> : a.source && <span>via {a.source}</span>}
                      <span title={fmtDateTime(a.created_at)}>{ago(a.created_at)}</span>
                      {calls && (
                        <span className="inline-flex items-center gap-1">
                          <Phone className="size-3.5" /> {calls}
                        </span>
                      )}
                      {a.booking && (
                        <Link href={reservationHref(a.booking)} className="font-mono font-semibold text-ink hover:underline">
                          {a.booking}
                        </Link>
                      )}
                    </p>
                    {(a.acknowledged_at || a.resolved_at) && (
                      <ol className="mt-3 space-y-1 border-l border-line pl-3 text-[12.5px] text-ink-2">
                        {a.acknowledged_at && (
                          <li>
                            <b className="font-semibold text-ink">Acknowledged</b> {fmtDateTime(a.acknowledged_at)}
                          </li>
                        )}
                        {a.resolved_at && (
                          <li>
                            <b className="font-semibold text-ink">Resolved</b> {fmtDateTime(a.resolved_at)}
                            {a.resolved_by && ` by ${a.resolved_by}`}
                            {a.resolution_note && <span className="block text-ink">“{a.resolution_note}”</span>}
                          </li>
                        )}
                      </ol>
                    )}
                  </div>
                  {a.status !== "resolved" && (
                    <div className="flex shrink-0 flex-wrap items-start gap-2 sm:flex-col sm:items-stretch">
                      {a.phone && (
                        <Button asChild variant={live ? "danger" : "soft"} size="sm">
                          <a href={`tel:${a.phone}`}>
                            <Phone className="size-4" /> Call guest
                          </a>
                        </Button>
                      )}
                      {a.status === "open" && (
                        <Button variant="soft" size="sm" loading={ack.isPending && ack.variables?.id === a.id} onClick={() => ack.mutate(a)}>
                          <Check className="size-4" /> Acknowledge
                        </Button>
                      )}
                      <Button
                        variant="dark"
                        size="sm"
                        onClick={() => {
                          setNote("");
                          setResolving(a);
                        }}
                      >
                        Resolve
                      </Button>
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <ConfirmDialog
        open={!!resolving}
        onOpenChange={(v) => !v && setResolving(null)}
        title="Resolve alert"
        confirmLabel="Mark resolved"
        loading={resolve.isPending}
        onConfirm={() => resolving && resolve.mutate({ a: resolving, note: note.trim() })}
      >
        <p className="text-ink">{resolving?.summary}</p>
        <Field label="What happened? (kept with the alert)">
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} placeholder="e.g. Caretaker reset the breaker, guest confirmed power is back" autoFocus />
        </Field>
      </ConfirmDialog>
    </div>
  );
}
