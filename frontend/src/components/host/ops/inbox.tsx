"use client";

import { keepPreviousData, useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import {
  ArrowLeft, Check, CheckCheck, CircleAlert, CircleCheck, Clock, Inbox as InboxIcon, Info, MessageSquare, Phone, Search, Send, Voicemail,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { ErrorBlock, StatusBadge } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Dialog, SheetContent } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Badge, Skeleton, Spinner } from "@/components/ui/misc";
import { Tooltip } from "@/components/ui/overlays";
import { get, post, qs } from "@/lib/api";
import { CHANNEL_LABEL, clock, fmtDate, fmtRange, kes, plural, relDay, toDate } from "@/lib/format";
import type { ChatMessage, TripCard } from "@/lib/types";
import { cn } from "@/lib/utils";

import { ChannelIcon, Flag, GuestAvatar, MiniEmpty, Segmented } from "./bits";
import { countryName, displayName, duration, fmtPhone, LANGUAGES, minutesSince, smsSegments, useDebounced, useHostAction, useNow } from "./lib";
import type { ThreadDetail, ThreadRow } from "./types";

type Filter = "needs_reply" | "all" | "staff";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "needs_reply", label: "Needs reply" },
  { value: "all", label: "Guests" },
  { value: "staff", label: "Staff" },
];

export function InboxView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const selected = Number(params.get("t")) || null;
  const [filter, setFilter] = React.useState<Filter>("all");
  const [search, setSearch] = React.useState("");
  const q = useDebounced(search.trim(), 300);

  const list = useQuery({
    queryKey: ["host", "ops", "inbox", filter, q],
    queryFn: () => get<ThreadRow[]>(`/api/host/inbox${qs({ filter, q })}`),
    refetchInterval: 5_000,
    placeholderData: keepPreviousData,
  });

  const select = (id: number | null) => router.replace(id ? `${pathname}?t=${id}` : pathname, { scroll: false });

  // fills the screen between the shell's chrome: 24px padding above and the 62px tab bar (+18px gap) below on phones,
  // the 81px header and 40px padding above (+24px gap below) from md, minus the SOS banner when it shows
  return (
    <div className="flex h-[calc(100dvh-104px-var(--sos-banner-h,0px))] min-h-[400px] overflow-hidden rounded-2xl border border-line-soft bg-white md:h-[calc(100dvh-145px-var(--sos-banner-h,0px))] md:min-h-[520px]">
      <aside className={cn("flex w-full min-w-0 flex-col md:w-[320px] md:shrink-0 md:border-r md:border-line-soft", selected && "hidden md:flex")}>
        <div className="space-y-3 border-b border-line-soft p-4">
          <div className="flex items-center justify-between gap-2">
            <h1 className="text-xl font-bold tracking-tight">Inbox</h1>
            {list.isFetching && list.data && <Spinner className="size-4" />}
          </div>
          <Segmented label="Show" size="sm" value={filter} onChange={setFilter} options={FILTERS} />
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
            <Input
              type="search"
              aria-label="Search conversations"
              placeholder="Search name, phone or message"
              className="h-9 pl-9 text-sm"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>
        <ThreadList query={list} selected={selected} onSelect={select} filter={filter} />
      </aside>

      {selected ? (
        <Conversation key={selected} id={selected} onBack={() => select(null)} />
      ) : (
        <div className="hidden flex-1 items-center justify-center md:flex">
          <MiniEmpty icon={<InboxIcon />} title="Pick a conversation">
            SMS, WhatsApp, web chat and voicemail from every guest land here — one thread per phone number.
          </MiniEmpty>
        </div>
      )}
    </div>
  );
}

// ---------- thread list ----------

function ThreadList({
  query, selected, onSelect, filter,
}: { query: UseQueryResult<ThreadRow[]>; selected: number | null; onSelect: (id: number) => void; filter: Filter }) {
  const now = useNow(30_000);
  if (query.isLoading) {
    return (
      <div className="space-y-4 p-4">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="flex gap-3">
            <Skeleton className="size-10 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-3.5 w-2/3" />
              <Skeleton className="h-3 w-full" />
            </div>
          </div>
        ))}
      </div>
    );
  }
  if (query.error && !query.data) {
    return (
      <div className="p-4">
        <ErrorBlock error={query.error} retry={() => query.refetch()} />
      </div>
    );
  }
  const threads = query.data ?? [];
  if (!threads.length) {
    return filter === "needs_reply" ? (
      <MiniEmpty icon={<CircleCheck className="text-success" />} title="Inbox zero">
        Every guest has an answer. The bot handles the routine questions — anything it can&apos;t answer lands here.
      </MiniEmpty>
    ) : (
      <MiniEmpty icon={<MessageSquare />} title="No conversations">
        Messages from guests on any channel will appear here.
      </MiniEmpty>
    );
  }
  return (
    <ul className="min-h-0 flex-1 divide-y divide-line-soft overflow-y-auto">
      {threads.map((t) => {
        const name = displayName(t.guest?.name, t.phone);
        const active = t.id === selected;
        const waited = minutesSince(t.waiting_since ?? t.last_message_at, now);
        return (
          <li key={t.id}>
            <button
              type="button"
              onClick={() => onSelect(t.id)}
              aria-current={active ? "true" : undefined}
              className={cn("flex w-full gap-3 px-4 py-3 text-left transition-colors hover:bg-surface", active && "bg-surface")}
            >
              <span className="relative shrink-0 self-start">
                <GuestAvatar name={t.guest?.name} size={40} />
                {t.guest?.nationality && <Flag code={t.guest.nationality} className="absolute -right-1 -bottom-1 text-[15px]" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline gap-2">
                  <span className={cn("truncate text-sm", t.unread ? "font-bold text-ink" : "font-semibold")}>{name}</span>
                  <span className={cn("ml-auto shrink-0 text-xs tabular-nums", t.unread ? "font-semibold text-brand-600" : "text-ink-3")}>
                    {clock(t.last_message_at)}
                  </span>
                </span>
                {t.booking ? (
                  <span className="block truncate text-xs text-ink-2">
                    {t.booking.unit} · {t.booking.status.replace("_", " ")}
                  </span>
                ) : t.guest && t.guest.role !== "guest" ? (
                  <span className="block truncate text-xs text-ink-2 capitalize">{t.guest.role}</span>
                ) : null}
                <span className={cn("mt-0.5 line-clamp-2 text-[13px] leading-snug", t.unread ? "text-ink" : "text-ink-2")}>{t.last_preview}</span>
                {t.needs_reply && (
                  <Badge tone={waited >= 30 ? "danger" : "warning"} className="mt-1.5 tabular-nums">
                    <Clock className="size-3" /> Waiting {duration(t.waiting_since ?? t.last_message_at, now)}
                  </Badge>
                )}
              </span>
              {t.unread > 0 && (
                <span className="mt-1 grid h-5 min-w-5 shrink-0 place-items-center rounded-full bg-brand-500 px-1 text-[11px] font-bold text-white">{t.unread}</span>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

// ---------- conversation ----------

function Conversation({ id, onBack }: { id: number; onBack: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["host", "ops", "thread", id],
    queryFn: () => get<ThreadDetail>(`/api/host/inbox/${id}`),
    refetchInterval: 4_000,
  });
  const [infoOpen, setInfoOpen] = React.useState(false);
  const scroller = React.useRef<HTMLDivElement>(null);
  const nearBottom = React.useRef(true);
  const count = q.data?.messages.length ?? 0;

  React.useEffect(() => {
    const el = scroller.current;
    if (el && nearBottom.current) el.scrollTop = el.scrollHeight;
  }, [count]);

  const resolve = useHostAction(() => post(`/api/host/inbox/${id}/resolve`), { success: "Marked as resolved" });

  if (q.error && !q.data) {
    return (
      <div className="flex-1 p-6">
        <ErrorBlock error={q.error} retry={() => q.refetch()} />
      </div>
    );
  }
  if (!q.data) {
    return (
      <div className="flex flex-1 flex-col">
        <div className="flex h-16 items-center gap-3 border-b border-line-soft px-4">
          <Skeleton className="size-9 rounded-full" />
          <Skeleton className="h-4 w-40" />
        </div>
        <div className="flex-1 space-y-4 p-6">
          <Skeleton className="h-14 w-2/3 rounded-2xl" />
          <Skeleton className="ml-auto h-14 w-1/2 rounded-2xl" />
          <Skeleton className="h-10 w-1/2 rounded-2xl" />
        </div>
      </div>
    );
  }

  const { thread, messages, bookings, quick_replies } = q.data;
  const name = displayName(thread.guest?.name, thread.phone);

  return (
    <>
      <section className="flex min-w-0 flex-1 flex-col" aria-label={`Conversation with ${name}`}>
        <header className="flex min-h-16 items-center gap-3 border-b border-line-soft px-3 py-2 sm:px-4">
          <Button variant="ghost" size="icon-sm" className="md:hidden" aria-label="Back to conversations" onClick={onBack}>
            <ArrowLeft className="size-4" />
          </Button>
          <GuestAvatar name={thread.guest?.name} size={36} />
          <div className="min-w-0 flex-1">
            <p className="flex items-center gap-1.5 truncate text-[15px] font-bold">
              {name} <Flag code={thread.guest?.nationality} />
            </p>
            <p className="truncate text-xs text-ink-2">
              {thread.guest?.name ? fmtPhone(thread.phone) : "Unknown number"}
              {thread.booking && (
                <>
                  {" · "}
                  <Link href={`/host/reservations/${thread.booking.ref}`} className="font-semibold text-ink hover:underline">
                    {thread.booking.unit} · {thread.booking.ref}
                  </Link>
                </>
              )}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {(thread.needs_reply || thread.status === "open") && (
              <Button size="sm" variant="soft" loading={resolve.isPending} onClick={() => resolve.mutate()}>
                <CircleCheck className="size-3.5" /> <span className="hidden sm:inline">Mark resolved</span>
                <span className="sm:hidden">Resolve</span>
              </Button>
            )}
            <Tooltip content="Call">
              <Button asChild variant="ghost" size="icon-sm">
                <a href={`tel:${thread.phone}`} aria-label={`Call ${name}`}>
                  <Phone className="size-4" />
                </a>
              </Button>
            </Tooltip>
            <Tooltip content="Guest & bookings">
              <Button variant="ghost" size="icon-sm" className="xl:hidden" aria-label="Guest and booking details" onClick={() => setInfoOpen(true)}>
                <Info className="size-4" />
              </Button>
            </Tooltip>
          </div>
        </header>

        <div
          ref={scroller}
          className="min-h-0 flex-1 overflow-y-auto bg-[linear-gradient(180deg,#fff,var(--color-surface))] px-3 py-4 sm:px-6"
          onScroll={(e) => {
            const el = e.currentTarget;
            nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
          }}
        >
          <Messages messages={messages} needsReply={thread.needs_reply} />
        </div>

        <Composer
          threadId={id}
          name={name}
          quickReplies={quick_replies}
          onSent={(payload) => {
            nearBottom.current = true;
            qc.setQueryData(["host", "ops", "thread", id], payload);
          }}
        />
      </section>

      <aside className="hidden w-[300px] shrink-0 flex-col overflow-y-auto border-l border-line-soft xl:flex">
        <ContextPanel thread={thread} bookings={bookings} />
      </aside>
      <Dialog open={infoOpen} onOpenChange={setInfoOpen}>
        <SheetContent title={name} width="max-w-sm">
          <ContextPanel thread={thread} bookings={bookings} />
        </SheetContent>
      </Dialog>
    </>
  );
}

function Messages({ messages, needsReply }: { messages: ChatMessage[]; needsReply: boolean }) {
  if (!messages.length) return <p className="py-10 text-center text-sm text-ink-2">No messages yet.</p>;
  return (
    <ol className="mx-auto max-w-3xl space-y-3">
      {messages.map((m, i) => {
        const sep = i === 0 || fmtDate(messages[i - 1].created_at, "yyyy-MM-dd") !== fmtDate(m.created_at, "yyyy-MM-dd");
        const pending = needsReply && m.direction === "in" && ["relayed", "pending", "escalated"].includes(m.handled) && !messages.slice(i + 1).some((x) => x.direction === "out" && (x.sender === "host" || x.sender === "staff"));
        return (
          <React.Fragment key={m.id}>
            {sep && (
              <li className="flex items-center gap-3 py-2" aria-hidden>
                <span className="h-px flex-1 bg-line-soft" />
                <span className="text-[11px] font-bold tracking-wider text-ink-3 uppercase">{relDay(m.created_at)}</span>
                <span className="h-px flex-1 bg-line-soft" />
              </li>
            )}
            <li>
              <Bubble m={m} waiting={pending} />
            </li>
          </React.Fragment>
        );
      })}
    </ol>
  );
}

const HANDLED: Record<string, string> = { auto: "Answered by the bot", relayed: "Sent to you", escalated: "Escalated", pending: "Waiting" };

function Bubble({ m, waiting }: { m: ChatMessage; waiting: boolean }) {
  const inbound = m.direction === "in";
  const human = m.sender === "host" || m.sender === "staff";
  const voicemail = m.body.startsWith("[voicemail]");
  const url = voicemail ? m.body.replace("[voicemail]", "").trim() : "";
  const autoLabel = m.sender === "bot" ? "Auto-reply" : m.sender === "system" ? (m.kind ? `Automated · ${m.kind.replace(/_/g, " ")}` : "Automated") : "";
  return (
    <div className={cn("flex", inbound ? "justify-start" : "justify-end")}>
      <div className={cn("flex max-w-[85%] flex-col sm:max-w-[75%]", inbound ? "items-start" : "items-end")}>
        {!inbound && !human && (
          <span className="mb-1 inline-flex items-center gap-1 text-[11px] font-semibold text-ocean-600">
            <span className="size-1.5 rounded-full bg-ocean-500" /> {autoLabel}
          </span>
        )}
        <div
          className={cn(
            "rounded-2xl px-3.5 py-2.5 text-[14px] leading-relaxed break-words whitespace-pre-wrap",
            inbound && "rounded-bl-md bg-surface text-ink ring-1 ring-line-soft",
            !inbound && human && "rounded-br-md bg-ink text-white",
            !inbound && !human && "rounded-br-md border border-ocean-100 bg-ocean-50 text-ink",
            waiting && "ring-2 ring-warning/40",
          )}
        >
          {voicemail ? (
            <div className="min-w-[220px]">
              <p className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold">
                <Voicemail className="size-4" /> Voicemail
              </p>
              <audio controls preload="none" src={url} className="h-9 w-full max-w-[280px]" />
            </div>
          ) : (
            m.body
          )}
        </div>
        <div className={cn("mt-1 flex flex-wrap items-center gap-1.5 px-1 text-[11px] text-ink-3", !inbound && "justify-end")}>
          <span className="inline-flex items-center gap-1 rounded-full border border-line-soft bg-white px-1.5 py-px font-semibold text-ink-2">
            <ChannelIcon channel={m.channel} className="size-3" />
            {m.channel === "web" ? "Web" : (CHANNEL_LABEL[m.channel] ?? m.channel.toUpperCase())}
          </span>
          <time dateTime={m.created_at}>{toDate(m.created_at).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}</time>
          {human && m.sent_by && <span>· {m.sent_by}</span>}
          {!inbound && <Ticks status={m.status} reason={m.failure_reason} />}
          {inbound && HANDLED[m.handled] && <span className={cn(waiting && "font-semibold text-warning")}>· {waiting ? "Waiting for you" : HANDLED[m.handled]}</span>}
        </div>
      </div>
    </div>
  );
}

function Ticks({ status, reason }: { status: string; reason: string }) {
  const map: Record<string, { icon: React.ComponentType<{ className?: string }>; label: string; cls: string }> = {
    queued: { icon: Clock, label: "Queued", cls: "text-ink-3" },
    sending: { icon: Clock, label: "Sending", cls: "text-ink-3" },
    sent: { icon: Check, label: "Sent", cls: "text-ink-2" },
    delivered: { icon: CheckCheck, label: "Delivered", cls: "text-ocean-600" },
    failed: { icon: CircleAlert, label: reason ? `Failed: ${reason}` : "Failed", cls: "text-danger" },
    logged: { icon: Check, label: "Logged (not sent by SMS)", cls: "text-ink-3" },
  };
  const s = map[status];
  if (!s) return null;
  return (
    <Tooltip content={s.label}>
      <span className={cn("inline-flex items-center gap-0.5", s.cls)} aria-label={s.label} role="img">
        <s.icon className="size-3.5" />
        {status === "failed" && <span className="font-semibold">Failed</span>}
      </span>
    </Tooltip>
  );
}

// ---------- composer ----------

const SEND_CHANNELS = [
  { value: "sms", label: "SMS" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "web", label: "Web chat" },
];

function Composer({ threadId, name, quickReplies, onSent }: { threadId: number; name: string; quickReplies: string[]; onSent: (p: ThreadDetail) => void }) {
  const [text, setText] = React.useState("");
  const [channel, setChannel] = React.useState("sms");
  const box = React.useRef<HTMLTextAreaElement>(null);
  const send = useHostAction(() => post<ThreadDetail>(`/api/host/inbox/${threadId}/reply`, { text: text.trim(), channel }), {
    success: `Sent to ${name.split(" ")[0]} by ${SEND_CHANNELS.find((c) => c.value === channel)?.label ?? "SMS"}`,
    onSuccess: (payload) => {
      setText("");
      onSent(payload);
    },
  });
  const submit = () => {
    if (text.trim() && !send.isPending) send.mutate();
  };
  const segments = smsSegments(text);

  return (
    <div className="border-t border-line-soft bg-white px-3 pt-3 pb-3 sm:px-4">
      {quickReplies.length > 0 && (
        <div className="no-scrollbar mb-2.5 flex gap-2 overflow-x-auto pb-0.5">
          {quickReplies.map((r) => (
            <button
              key={r}
              type="button"
              title={r}
              onClick={() => {
                setText((cur) => (cur.trim() ? `${cur.trim()} ${r}` : r));
                box.current?.focus();
              }}
              className="max-w-[260px] shrink-0 truncate rounded-full border border-line px-3 py-1.5 text-[13px] text-ink-2 transition-colors hover:border-ink hover:text-ink"
            >
              {r}
            </button>
          ))}
        </div>
      )}
      <form
        className="flex items-end gap-2 rounded-2xl border border-line bg-white p-2 transition-colors focus-within:border-ink"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <textarea
          ref={box}
          aria-label={`Reply to ${name}`}
          rows={2}
          maxLength={1000}
          placeholder={`Reply to ${name.split(" ")[0]}…`}
          className="max-h-40 min-h-11 flex-1 resize-none bg-transparent px-2 py-1.5 text-[15px] leading-relaxed outline-none field-sizing-content placeholder:text-ink-3"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <select
          aria-label="Send as"
          value={channel}
          onChange={(e) => setChannel(e.target.value)}
          className="h-9 rounded-lg border border-line bg-white px-2 text-[13px] font-semibold text-ink-2 outline-none hover:border-ink focus-visible:border-ink"
        >
          {SEND_CHANNELS.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
        <Button type="submit" variant="dark" size="sm" className="h-9" loading={send.isPending} disabled={!text.trim()} aria-label="Send reply">
          <Send className="size-3.5" /> <span className="hidden sm:inline">Send</span>
        </Button>
      </form>
      <div className="mt-1.5 flex items-center justify-between px-1 text-[11px] text-ink-3">
        <span>
          <kbd className="font-sans">⌘</kbd>/<kbd className="font-sans">Ctrl</kbd> + Enter to send
        </span>
        {text && (
          <span className="tabular-nums">
            {text.length} chars{channel === "sms" && ` · ${plural(segments, "SMS", "SMS")}`}
          </span>
        )}
      </div>
    </div>
  );
}

// ---------- context ----------

function ContextPanel({ thread, bookings }: { thread: ThreadRow; bookings: TripCard[] }) {
  const g = thread.guest;
  const name = displayName(g?.name, thread.phone);
  const stays = bookings.filter((b) => ["completed", "checked_in", "confirmed"].includes(b.status));
  const value = stays.reduce((n, b) => n + b.total, 0);
  return (
    <div className="space-y-6 p-5">
      <div className="text-center">
        <div className="mx-auto w-fit">
          <GuestAvatar name={g?.name} size={64} />
        </div>
        <p className="mt-3 text-base font-bold">{name}</p>
        <p className="text-[13px] text-ink-2 tabular-nums">{fmtPhone(thread.phone)}</p>
        <div className="mt-3 flex justify-center gap-2">
          <Button asChild size="sm" variant="soft">
            <a href={`tel:${thread.phone}`}>
              <Phone className="size-3.5" /> Call
            </a>
          </Button>
          {g && (
            <Button asChild size="sm" variant="soft">
              <Link href={`/host/guests?guest=${g.id}`}>Profile</Link>
            </Button>
          )}
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-3 text-sm">
        <Fact label="From">
          {g?.nationality ? (
            <span className="inline-flex items-center gap-1">
              <Flag code={g.nationality} /> {countryName(g.nationality)}
            </span>
          ) : (
            "—"
          )}
        </Fact>
        <Fact label="Language">{g ? (LANGUAGES[g.lang] ?? g.lang) : "—"}</Fact>
        <Fact label="Stays">{stays.length}</Fact>
        <Fact label="Booked value">{value ? kes(value) : "—"}</Fact>
        {g && g.role !== "guest" && <Fact label="Role">{g.role}</Fact>}
      </dl>

      <div>
        <p className="mb-2 text-[11px] font-bold tracking-wider text-ink-3 uppercase">Bookings</p>
        {bookings.length === 0 ? (
          <p className="rounded-xl bg-surface px-3 py-4 text-center text-[13px] text-ink-2">No bookings for this number yet.</p>
        ) : (
          <ul className="space-y-2">
            {bookings.map((b) => (
              <li key={b.ref}>
                <Link
                  href={`/host/reservations/${b.ref}`}
                  className={cn(
                    "flex gap-3 rounded-xl border p-2.5 transition-colors hover:border-ink-3",
                    b.ref === thread.booking?.ref ? "border-ink/40 bg-surface/60" : "border-line-soft",
                  )}
                >
                  {b.unit.cover ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={b.unit.cover} alt="" className="size-12 shrink-0 rounded-lg bg-surface object-cover" />
                  ) : (
                    <span className="size-12 shrink-0 rounded-lg bg-surface" />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-semibold">{b.unit.name}</span>
                    <span className="block text-xs text-ink-2">
                      {fmtRange(b.check_in, b.check_out)} · {b.ref}
                    </span>
                    <span className="mt-1 flex items-center gap-1.5">
                      <StatusBadge status={b.status} label={b.status_label} />
                      {b.balance_due > 0 && !["cancelled", "completed", "expired"].includes(b.status) && (
                        <span className="text-[11px] font-semibold text-warning tabular-nums">{kes(b.balance_due)} due</span>
                      )}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-surface px-3 py-2.5">
      <dt className="text-[11px] font-semibold text-ink-2">{label}</dt>
      <dd className="mt-0.5 truncate font-semibold capitalize">{children}</dd>
    </div>
  );
}
