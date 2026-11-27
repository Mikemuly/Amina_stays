"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, Bot, MessageCircle, Phone, Smartphone } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { useConfig, useMe } from "@/components/providers";
import { AuthGate } from "@/components/site/auth-gate";
import { SiteHeader } from "@/components/site/header";
import { Logo } from "@/components/host/shell";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { get, post } from "@/lib/api";
import { fmtDate, fmtTime } from "@/lib/format";
import type { ChatMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

const QUICK = ["Directions", "Wi-Fi", "Breakfast", "Checkout time", "Price list", "Late checkout"];
const CHANNEL: Record<string, string> = { sms: "SMS", web: "Web", ussd: "USSD", voice: "Voice", whatsapp: "WhatsApp", system: "" };

export function MessagesView() {
  return (
    <AuthGate title="Log in to message Amina">
      <Messages />
    </AuthGate>
  );
}

function Messages() {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const { data: config } = useConfig();
  const { data, isLoading } = useQuery({
    queryKey: ["messages"],
    queryFn: () => get<{ messages: ChatMessage[]; host: string }>("/api/messages"),
    refetchInterval: 4000,
  });
  const [text, setText] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const listRef = React.useRef<HTMLDivElement>(null);
  const count = data?.messages.length ?? 0;
  React.useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [count]);

  async function send(body: string) {
    if (!body.trim()) return;
    setSending(true);
    try {
      const r = await post<{ messages: ChatMessage[]; host: string }>("/api/messages", { body });
      qc.setQueryData(["messages"], r);
      setText("");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSending(false);
    }
  }

  const groups: { day: string; items: ChatMessage[] }[] = [];
  for (const m of data?.messages ?? []) {
    const day = fmtDate(m.created_at, "EEEE d MMMM");
    if (groups.at(-1)?.day !== day) groups.push({ day, items: [] });
    groups.at(-1)!.items.push(m);
  }

  return (
    <>
      <SiteHeader />
      <main className="container-narrow max-w-[860px] pt-6 pb-28 md:pb-10">
        <div className="flex h-[calc(100dvh-160px)] min-h-[520px] flex-col overflow-hidden rounded-2xl border border-line-soft md:h-[calc(100dvh-140px)]">
          <div className="flex items-center gap-3 border-b border-line-soft px-5 py-4">
            <Logo className="size-11 rounded-full" />
            <div className="min-w-0 flex-1">
              <p className="font-bold">{data?.host ?? "Amina"} · Amina Stays</p>
              <p className="text-sm text-ink-2">Instant answers 24/7 · Amina replies personally within the hour</p>
            </div>
            {config?.channels.voice_number && (
              <Button asChild variant="soft" size="sm"><a href={`tel:${config.channels.voice_number}`}><Phone className="size-4" /> Call</a></Button>
            )}
          </div>

          <div ref={listRef} className="flex-1 overflow-y-auto bg-surface/40 px-4 py-6 sm:px-6">
            {isLoading ? (
              <div className="space-y-4">{[0, 1, 2].map((i) => <Skeleton key={i} className={cn("h-14 w-2/3 rounded-2xl", i % 2 && "ml-auto")} />)}</div>
            ) : !count ? (
              <div className="grid h-full place-items-center text-center">
                <div className="max-w-sm">
                  <MessageCircle className="mx-auto size-10 text-ink-3" strokeWidth={1.4} />
                  <p className="mt-4 text-lg font-semibold">Ask Amina anything</p>
                  <p className="mt-1 text-ink-2">Prices, availability, breakfast, directions, Wi-Fi… This is the same conversation as SMS to {config?.channels.sms_number || "our number"} — switch any time.</p>
                </div>
              </div>
            ) : (
              <div className="space-y-6">
                {groups.map((g) => (
                  <div key={g.day} className="space-y-3">
                    <p className="text-center text-xs font-semibold text-ink-2">{g.day}</p>
                    {g.items.map((m) => <Bubble key={m.id} m={m} me={me?.name} />)}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="border-t border-line-soft p-3 sm:p-4">
            <div className="mb-3 flex gap-2 overflow-x-auto pb-1 no-scrollbar">
              {QUICK.map((q) => (
                <button key={q} onClick={() => send(q)} disabled={sending} className="shrink-0 rounded-full border border-line px-3.5 py-1.5 text-sm font-medium hover:border-ink disabled:opacity-50">{q}</button>
              ))}
            </div>
            <form onSubmit={(e) => { e.preventDefault(); send(text); }} className="flex items-end gap-2">
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }}
                rows={1}
                placeholder="Write a message…"
                className="max-h-32 min-h-12 flex-1 resize-none rounded-3xl border border-line px-5 py-3 text-[15px] outline-none focus:border-ink"
              />
              <button type="submit" disabled={sending || !text.trim()} aria-label="Send" className="grid size-12 shrink-0 place-items-center rounded-full bg-brand-500 text-white transition disabled:bg-line">
                <ArrowUp className="size-5" strokeWidth={2.5} />
              </button>
            </form>
            <p className="mt-2 flex items-center justify-center gap-1.5 text-xs text-ink-2">
              <Smartphone className="size-3" /> In an emergency text <b className="text-ink">HELP</b> or call <b className="text-ink">999</b>. <Link href="/help" className="underline">Help centre</Link>
            </p>
          </div>
        </div>
      </main>
    </>
  );
}

function Bubble({ m, me }: { m: ChatMessage; me?: string }) {
  const mine = m.direction === "in";
  const who = mine ? me || "You" : m.sender === "bot" ? "Amina's assistant" : m.sender === "host" ? m.sent_by || "Amina" : m.sender === "staff" ? m.sent_by || "Amina's team" : "Amina Stays";
  return (
    <div className={cn("flex", mine ? "justify-end" : "justify-start")}>
      <div className={cn("max-w-[85%] sm:max-w-[70%]")}>
        <div className={cn("rounded-3xl px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-line", mine ? "rounded-br-lg bg-ink text-white" : "rounded-bl-lg border border-line-soft bg-white")}>
          <Linkified text={m.body} light={mine} />
        </div>
        <p className={cn("mt-1 flex items-center gap-1 px-2 text-[11px] text-ink-2", mine && "justify-end")}>
          {!mine && m.sender === "bot" && <Bot className="size-3" />}
          {who} · {fmtTime(m.created_at)}{CHANNEL[m.channel] ? ` · ${CHANNEL[m.channel]}` : ""}
          {m.status === "failed" && <span className="text-danger"> · not delivered</span>}
        </p>
      </div>
    </div>
  );
}

const URL_RE = /(https?:\/\/[^\s]*[^\s.,;:!?)])/g;

function Linkified({ text, light }: { text: string; light: boolean }) {
  return (
    <>
      {text.split(URL_RE).map((part, i) =>
        i % 2 ? (
          <a key={i} href={part} rel="noreferrer" className={cn("break-all underline", light ? "text-white" : "text-ocean-700")}>
            {part.replace(/^https?:\/\//, "")}
          </a>
        ) : (
          part
        ),
      )}
    </>
  );
}
