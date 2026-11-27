"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowUp, CalendarClock, CheckCheck, Delete, FlaskConical, Landmark, Mic, Phone, PhoneIncoming, PhoneOff, RotateCcw, Signal, Smartphone, Sparkles, UserRound,
  Volume2, VolumeX, Wifi, WifiOff, Zap,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Logo } from "@/components/host/shell";
import { useConfig, usePayOptions } from "@/components/providers";
import { SiteHeader } from "@/components/site/header";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { Badge, Skeleton } from "@/components/ui/misc";
import { get, post } from "@/lib/api";
import { clock } from "@/lib/format";
import type { DemoPersona } from "@/lib/types";
import { cn, flag } from "@/lib/utils";

type DemoMsg = { id: number; direction: "in" | "out"; channel: string; body: string; status: string; kind: string; created_at: string };

const NEW_GUEST: DemoPersona = { phone: "+254722000111", name: "New guest", role: "guest", lang: "en", ref: null, note: "No account yet — try booking" };
const COUNTRY_BY_PREFIX: [string, string][] = [["+254", "KE"], ["+39", "IT"], ["+49", "DE"], ["+44", "GB"], ["+33", "FR"], ["+1", "US"]];
const countryOf = (phone: string) => COUNTRY_BY_PREFIX.find(([p]) => phone.startsWith(p))?.[1] ?? "";

export function DemoLab() {
  const { data: config, isLoading } = useConfig();
  const lab = config?.demo_lab;
  const [phone, setPhone] = React.useState(NEW_GUEST.phone);

  if (isLoading) return <><SiteHeader /><main className="container-site py-10"><Skeleton className="h-[640px] rounded-3xl" /></main></>;
  if (!config?.demo || !lab) {
    return (
      <>
        <SiteHeader />
        <main className="container-narrow max-w-[640px] py-24 text-center">
          <FlaskConical className="mx-auto size-12 text-ink-3" />
          <h1 className="mt-4 text-2xl font-bold">The Demo Lab is switched off</h1>
          <p className="mt-2 text-ink-2">Start the backend with <code className="rounded bg-surface px-1.5">DEMO=1</code> to simulate SMS, USSD and voice in the browser.</p>
        </main>
      </>
    );
  }
  const people = [NEW_GUEST, ...lab.guests];
  const host: DemoPersona = { phone: lab.host_phone, name: lab.host_name, role: "host", lang: "en", ref: null, note: "" };
  const current = [...people, ...lab.staff, host].find((p) => p.phone === phone);

  return (
    <>
      <SiteHeader />
      <main className="pb-24">
        <section className="border-b border-line-soft bg-gradient-to-b from-sand-50 to-white">
          <div className="container-site py-10">
            <div className="flex flex-wrap items-end justify-between gap-6">
              <div className="max-w-2xl">
                <Badge tone="ocean" className="mb-3"><FlaskConical className="size-3" /> Demo Lab</Badge>
                <h1 className="text-[32px] leading-tight font-bold tracking-tight sm:text-[40px]">Every channel, live — no phone needed</h1>
                <p className="mt-3 text-lg text-ink-2">
                  These phones post to the <b className="text-ink">same webhooks Africa&apos;s Talking calls in production</b> — USSD, SMS and Voice — so you can book, pay and
                  receive a door code end to end. Everything also appears in the <Link href="/host" className="font-semibold text-ink underline">host console</Link>.
                </p>
              </div>
              <ResetButton />
            </div>
            <PersonaBar people={people} staff={lab.staff} hostPhone={lab.host_phone} phone={phone} setPhone={setPhone} />
          </div>
        </section>

        <div className="container-site mt-10">
          <div className="mb-5 flex flex-wrap items-center gap-3">
            <h2 className="text-[22px] font-bold tracking-tight">You&apos;re holding {current?.name ?? phone}&apos;s phone</h2>
            <span className="font-mono text-sm text-ink-2">{flag(countryOf(phone))} {phone}</span>
            {current?.ref && <Link href={`/host/reservations/${current.ref}`} className="text-sm font-semibold underline">{current.ref}</Link>}
          </div>
          <div className="grid grid-cols-1 justify-items-center gap-8 md:grid-cols-2 xl:grid-cols-3">
            <PhoneFrame label="SMS · “Ask Amina”" hint="Two-way SMS · English, Kiswahili, Italian, German, French">
              <SmsPhone key={`sms-${phone}`} phone={phone} contact={config.channels.sms_number || "AMINA"} suggestions={["Hi", "Bei", "BOOK", "Diani 12 Dec 3 nights 2 people", "BREAKFAST", "WIFI", "EXPLORE", "ALERTS", "COMPLAIN the music next door is too loud", "TICKETS", "POINTS", "HELP"]} />
            </PhoneFrame>
            <PhoneFrame label={`USSD · ${config.channels.ussd_code || "*384*…#"}`} hint="No data, any phone · 160-character screens">
              <UssdPhone key={`ussd-${phone}`} phone={phone} code={config.channels.ussd_code} />
            </PhoneFrame>
            <PhoneFrame label="Voice · “Call Amina”" hint="English & Kiswahili IVR · spoken aloud">
              <VoicePhone key={`voice-${phone}`} phone={phone} isHost={phone === lab.host_phone} />
            </PhoneFrame>
          </div>

          <div className="mt-14 grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
            <section className="min-w-0">
              <h2 className="text-[22px] font-bold tracking-tight">{lab.host_name}&apos;s phone</h2>
              <p className="mt-1 text-ink-2">Amina runs everything by SMS too: approve requests (<code className="text-ink">YES 12</code>), reply to a guest (<code className="text-ink">#3 Karibu!</code>), answer a ticket (<code className="text-ink">T1 Pole sana</code>, <code className="text-ink">CALL T1</code>), post an outage (<code className="text-ink">OUTAGE POWER ALL</code>) and acknowledge alerts (<code className="text-ink">OK</code>).</p>
              <div className="mt-5 flex justify-center lg:justify-start">
                <PhoneFrame label={`${lab.host_name} · host`} hint={lab.host_phone}>
                  <SmsPhone phone={lab.host_phone} contact="Amina Stays" suggestions={["OK", "STATUS", "TICKETS", "ALERTS", "OUTAGE WIFI ALL the router is being replaced", "#1 Karibu sana!"]} />
                </PhoneFrame>
              </div>
            </section>
            <TimeMachine guests={lab.guests} />
          </div>
        </div>
      </main>
    </>
  );
}

function PersonaBar({ people, staff, hostPhone, phone, setPhone }: { people: DemoPersona[]; staff: DemoPersona[]; hostPhone: string; phone: string; setPhone: (p: string) => void }) {
  const [custom, setCustom] = React.useState("");
  const chip = (active: boolean) => cn("flex shrink-0 items-center gap-3 rounded-2xl border bg-white px-4 py-2.5 text-left transition", active ? "border-ink ring-1 ring-ink" : "border-line-soft hover:border-ink");
  return (
    <div className="mt-8">
      <p className="text-sm font-semibold text-ink-2">Pick whose phone to hold</p>
      <div className="mt-3 flex gap-2 overflow-x-auto pb-2 no-scrollbar">
        {people.map((p) => (
          <button key={p.phone} onClick={() => setPhone(p.phone)} className={chip(phone === p.phone)}>
            <span className="text-xl">{p.ref ? flag(countryOf(p.phone)) : <Sparkles className="size-5 text-brand-500" />}</span>
            <span>
              <span className="block text-sm font-semibold">{p.name}</span>
              <span className="block max-w-56 truncate text-xs text-ink-2">{p.note}</span>
            </span>
          </button>
        ))}
        {[...staff, { phone: hostPhone, name: "Amina", role: "owner", lang: "en", ref: null, note: "Host / owner" }].map((p) => (
          <button key={p.phone} onClick={() => setPhone(p.phone)} className={chip(phone === p.phone)}>
            <UserRound className="size-5 text-ocean-600" />
            <span>
              <span className="block text-sm font-semibold">{p.name.split(" ")[0]}</span>
              <span className="block text-xs text-ink-2">{p.note}</span>
            </span>
          </button>
        ))}
      </div>
      <form className="mt-2 flex max-w-md gap-2" onSubmit={(e) => { e.preventDefault(); if (custom.trim()) setPhone(custom.replace(/\s+/g, "").replace(/^0/, "+254")); }}>
        <Input value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="…or any number, e.g. 0712 345 678" className="h-10" />
        <Button type="submit" variant="soft">Use</Button>
      </form>
    </div>
  );
}

function PhoneFrame({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) {
  return (
    <div className="w-full min-w-0 max-w-[340px]">
      <div className="mb-3 text-center">
        <p className="font-bold">{label}</p>
        <p className="text-xs text-ink-2">{hint}</p>
      </div>
      <div className="relative h-[620px] overflow-hidden rounded-[44px] border-[10px] border-ink bg-white shadow-card">
        <div className="absolute top-2 left-1/2 z-20 h-5 w-24 -translate-x-1/2 rounded-full bg-ink" />
        <div className="flex h-full flex-col">
          <div className="flex h-9 shrink-0 items-end justify-between px-6 pb-1 text-[11px] font-semibold">
            <span>Safaricom</span>
            <span className="flex items-center gap-1"><Signal className="size-3" /><Wifi className="size-3" /> 87%</span>
          </div>
          <div className="relative min-h-0 flex-1">{children}</div>
        </div>
      </div>
    </div>
  );
}

// ---------- SMS ----------

function useInbox(phone: string) {
  const [msgs, setMsgs] = React.useState<DemoMsg[]>([]);
  const last = React.useRef(0);
  const merge = React.useCallback((incoming: DemoMsg[]) => {
    if (!incoming.length) return;
    last.current = Math.max(last.current, ...incoming.map((m) => m.id));
    setMsgs((cur) => {
      const seen = new Set(cur.map((m) => m.id));
      return [...cur, ...incoming.filter((m) => !seen.has(m.id))].sort((a, b) => a.id - b.id);
    });
  }, []);
  React.useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const r = await get<{ messages: DemoMsg[] }>(`/api/demo/phone/${encodeURIComponent(phone)}?after=${last.current}`);
        if (alive) merge(r.messages);
      } catch {
        /* backend restarting — try again next tick */
      }
    };
    tick();
    const t = setInterval(tick, 2000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [phone, merge]);
  return { msgs, merge };
}

// http(s) links in a text, as a phone shows them (a trailing full stop or bracket stays outside the link)
const LINK_RE = /(https?:\/\/[^\s]*[^\s.,;:!?)])/g;

/** SMS text with tappable links, like a real phone: the card payment link opens in a new tab. */
function Linkified({ text }: { text: string }) {
  return (
    <>
      {text.split(LINK_RE).map((part, i) =>
        i % 2 ? (
          <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="font-medium underline underline-offset-2">{part}</a>
        ) : (
          part
        ),
      )}
    </>
  );
}

function SmsPhone({ phone, contact, suggestions }: { phone: string; contact: string; suggestions: string[] }) {
  const { msgs, merge } = useInbox(phone);
  const [text, setText] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const list = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (list.current) list.current.scrollTop = list.current.scrollHeight;
  }, [msgs.length]);

  async function send(body: string) {
    if (!body.trim()) return;
    setBusy(true);
    try {
      const r = await post<{ messages: DemoMsg[] }>("/api/demo/sms", { from: phone, text: body });
      merge(r.messages);
      setText("");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-col items-center border-b border-line-soft pb-2">
        <Logo className="size-9 rounded-full" />
        <p className="mt-1 text-xs font-semibold">{contact}</p>
      </div>
      <div ref={list} className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 py-3">
        {!msgs.length && <p className="pt-16 text-center text-xs text-ink-2">No messages yet.<br />Say hi — try English or Kiswahili.</p>}
        {msgs.map((m) => {
          // From the handset's point of view: "in" (to Amina Stays) is what this phone sent.
          const mine = m.direction === "in";
          return (
            <div key={m.id} className={cn("flex", mine ? "justify-end" : "justify-start")}>
              <div className={cn("max-w-[85%] rounded-2xl px-3 py-2 text-[13px] leading-snug whitespace-pre-line [overflow-wrap:anywhere]", mine ? "rounded-br-md bg-[#0b84ff] text-white" : "rounded-bl-md bg-[#e9e9eb] text-ink")}>
                <Linkified text={m.body} />
                <span className={cn("mt-0.5 block text-right text-[9px]", mine ? "text-white/70" : "text-ink-2")}>
                  {clock(m.created_at)}{m.channel !== "sms" ? ` · ${m.channel}` : ""}{!mine && m.status === "failed" ? " · failed" : ""}
                </span>
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex gap-1.5 overflow-x-auto px-2 pb-2 no-scrollbar">
        {suggestions.map((s) => (
          <button key={s} disabled={busy} onClick={() => send(s)} className="shrink-0 rounded-full border border-line px-2.5 py-1 text-[11px] font-medium hover:border-ink disabled:opacity-50">{s}</button>
        ))}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); send(text); }} className="flex items-center gap-2 border-t border-line-soft p-2">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Text message" aria-label="SMS text" className="h-9 min-w-0 flex-1 rounded-full border border-line px-3 text-sm outline-none focus:border-ink" />
        <button type="submit" disabled={busy || !text.trim()} aria-label="Send SMS" className="grid size-9 shrink-0 place-items-center rounded-full bg-[#0b84ff] text-white disabled:bg-line">
          <ArrowUp className="size-4" strokeWidth={2.6} />
        </button>
      </form>
    </div>
  );
}

// ---------- USSD ----------

function UssdPhone({ phone, code }: { phone: string; code?: string }) {
  const [session, setSession] = React.useState<string | null>(null);
  const [chain, setChain] = React.useState<string[]>([]);
  const [screen, setScreen] = React.useState("");
  const [ended, setEnded] = React.useState(false);
  const [input, setInput] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  async function request(sid: string, parts: string[]) {
    setBusy(true);
    try {
      const r = await post<{ response: string }>("/api/demo/ussd", { phone, text: parts.join("*"), session: sid });
      setScreen(r.response.replace(/^(CON|END)\s?/, ""));
      setEnded(r.response.startsWith("END"));
      setChain(parts);
    } catch (e) {
      setScreen((e as Error).message);
      setEnded(true);
    } finally {
      setBusy(false);
      setInput("");
    }
  }
  const dial = () => {
    const sid = `demo-${Date.now()}`;
    setSession(sid);
    setScreen("");
    request(sid, []);
  };
  const close = () => {
    setSession(null);
    setScreen("");
    setChain([]);
    setEnded(false);
  };

  return (
    <div className="flex h-full flex-col bg-[#101418] text-white">
      {!session ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6">
          <p className="font-mono text-3xl tracking-wider">{code || "*384*…#"}</p>
          <p className="text-center text-xs text-white/60">Works on every Kenyan phone — even a feature phone with no internet.</p>
          <button onClick={dial} aria-label="Dial USSD code" className="grid size-16 place-items-center rounded-full bg-success text-white shadow-lg transition hover:scale-105">
            <Phone className="size-7" />
          </button>
        </div>
      ) : (
        <div className="flex flex-1 items-center justify-center bg-black/40 p-4">
          <div className="w-full rounded-2xl bg-white p-4 text-ink shadow-xl">
            {busy && !screen ? (
              <p className="py-6 text-center text-sm text-ink-2">USSD code running…</p>
            ) : (
              <p className="min-h-24 font-mono text-[12.5px] leading-snug whitespace-pre-line [overflow-wrap:anywhere]">{screen}</p>
            )}
            {!ended ? (
              <form onSubmit={(e) => { e.preventDefault(); if (input.trim()) request(session, [...chain, input.trim()]); }}>
                <input autoFocus value={input} onChange={(e) => setInput(e.target.value)} disabled={busy} className="mt-3 h-10 w-full border-b-2 border-[#0e8388] font-mono text-sm outline-none" aria-label="USSD reply" />
                <div className="mt-3 flex justify-end gap-5 text-sm font-bold text-[#0e8388]">
                  <button type="button" onClick={close}>CANCEL</button>
                  <button type="submit" disabled={busy || !input.trim()}>SEND</button>
                </div>
              </form>
            ) : (
              <div className="mt-3 flex justify-end text-sm font-bold text-[#0e8388]"><button onClick={close}>OK</button></div>
            )}
            <p className="mt-2 text-right text-[10px] text-ink-3">{screen.length}/160 chars · 0 back · 00 home</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------- Voice ----------

type Line = { who: "ivr" | "me" | "sys"; text: string };
type CallState = "idle" | "active" | "digits" | "record" | "dial" | "ended";

function VoicePhone({ phone, isHost }: { phone: string; isHost: boolean }) {
  const [state, setState] = React.useState<CallState>("idle");
  const [lines, setLines] = React.useState<Line[]>([]);
  const [buffer, setBuffer] = React.useState("");
  const [speakOn, setSpeakOn] = React.useState(true);
  const [seconds, setSeconds] = React.useState(0);
  const [dialTo, setDialTo] = React.useState("");
  const call = React.useRef({ id: 0, session: "", direction: "Inbound", requestId: "" });
  const sessionPrefix = React.useRef("");
  React.useEffect(() => {
    sessionPrefix.current = Math.random().toString(36).slice(2, 10); // unique per page load: AT session ids never repeat
  }, []);
  const waiter = React.useRef<{ resolve: (v: string | null) => void; need: number } | null>(null);
  const bufRef = React.useRef("");
  const speakRef = React.useRef(true);
  const list = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    speakRef.current = speakOn;
    if (!speakOn) window.speechSynthesis?.cancel();
  }, [speakOn]);
  React.useEffect(() => {
    if (list.current) list.current.scrollTop = list.current.scrollHeight;
  }, [lines.length]);
  React.useEffect(() => {
    if (state === "idle" || state === "ended") return;
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [state]);
  React.useEffect(() => () => window.speechSynthesis?.cancel(), []);

  const add = (l: Line) => setLines((cur) => [...cur, l]);

  const speak = (text: string, sw: boolean, id: number) =>
    new Promise<void>((resolve) => {
      if (call.current.id !== id) return resolve();
      add({ who: "ivr", text });
      const synth = window.speechSynthesis;
      if (!speakRef.current || !synth) return void setTimeout(resolve, Math.min(600 + text.length * 18, 2600));
      const u = new SpeechSynthesisUtterance(text);
      u.lang = sw ? "sw-KE" : "en-GB";
      u.rate = 1.05;
      const safety = setTimeout(resolve, 1500 + text.length * 90);
      u.onend = u.onerror = () => {
        clearTimeout(safety);
        resolve();
      };
      synth.speak(u);
    });

  const waitDigits = (need: number, timeoutMs: number) =>
    new Promise<string | null>((resolve) => {
      bufRef.current = "";
      setBuffer("");
      const t = setTimeout(() => {
        waiter.current = null;
        resolve(null);
      }, timeoutMs);
      waiter.current = {
        need,
        resolve: (v) => {
          clearTimeout(t);
          waiter.current = null;
          resolve(v);
        },
      };
    });

  async function send(id: number, extra: Record<string, string>) {
    const r = await post<{ xml: string }>("/api/demo/voice", {
      phone,
      session: call.current.session,
      direction: call.current.direction,
      ...(call.current.requestId ? { clientRequestId: call.current.requestId } : {}),
      ...extra,
    });
    if (call.current.id === id) await run(r.xml, id);
  }

  // Plays an Africa's Talking voice XML response: <Say>, <GetDigits>, <Record>, <Dial>.
  async function run(xml: string, id: number): Promise<void> {
    if (!xml) return;
    const doc = new DOMParser().parseFromString(xml, "text/xml");
    const sw = (el: Element) => el.getAttribute("voice") === "swahili";
    for (const n of Array.from(doc.documentElement.children)) {
      if (call.current.id !== id) return;
      if (n.tagName === "Say") {
        await speak(n.textContent ?? "", sw(n), id);
      } else if (n.tagName === "GetDigits") {
        for (const s of Array.from(n.getElementsByTagName("Say"))) await speak(s.textContent ?? "", sw(s), id);
        if (call.current.id !== id) return;
        setState("digits");
        const digits = await waitDigits(Number(n.getAttribute("numDigits") || 1), Number(n.getAttribute("timeout") || 15) * 1000);
        if (call.current.id !== id) return;
        setState("active");
        if (digits === null) continue; // no input: fall through to the goodbye <Say>
        add({ who: "me", text: `Pressed ${digits}` });
        return send(id, { digits });
      } else if (n.tagName === "Record") {
        for (const s of Array.from(n.getElementsByTagName("Say"))) await speak(s.textContent ?? "", sw(s), id);
        if (call.current.id !== id) return;
        setState("record");
        await waitDigits(99, 90_000);
        if (call.current.id !== id) return;
        setState("active");
        add({ who: "me", text: "Voice message recorded" });
        return send(id, { recordingUrl: `https://demo.aminastays.local/voicemail/${call.current.session}.mp3` });
      } else if (n.tagName === "Dial") {
        const to = n.getAttribute("phoneNumbers") ?? "";
        setDialTo(to);
        add({ who: "sys", text: `Connecting to ${to}…` });
        setState("dial");
        return;
      }
    }
    finish(id, {});
  }

  function finish(id: number, extra: Record<string, string>) {
    if (call.current.id !== id) return;
    window.speechSynthesis?.cancel();
    setState("ended");
    add({ who: "sys", text: "Call ended" });
    post("/api/demo/voice", { phone, session: call.current.session, direction: call.current.direction, hangup: true, ...extra }).catch(() => undefined);
  }

  function start(direction: "Inbound" | "Outbound", requestId = "") {
    const id = call.current.id + 1;
    call.current = { id, session: `demo-voice-${sessionPrefix.current}-${id}`, direction, requestId };
    const intro = requestId ? "Call-back from Amina Stays support" : direction === "Outbound" ? "Incoming safety call from Amina Stays" : "Calling Amina Stays…";
    setLines([{ who: "sys", text: intro }]);
    setSeconds(0);
    setState("active");
    send(id, {}).catch((e) => {
      toast.error((e as Error).message);
      setState("ended");
    });
  }

  function hangup() {
    const id = call.current.id;
    finish(id, {});
    call.current = { ...call.current, id: id + 1 };
    waiter.current?.resolve(null);
  }

  function press(k: string) {
    if (!waiter.current) return;
    if (k === "#") return waiter.current.resolve(bufRef.current || "#");
    bufRef.current += k;
    setBuffer(bufRef.current);
    if (bufRef.current.length >= waiter.current.need) waiter.current.resolve(bufRef.current);
  }

  if (state === "idle") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-6 bg-gradient-to-b from-[#16202a] to-[#0b1016] px-6 text-white">
        <Logo className="size-16 rounded-full" />
        <div className="text-center">
          <p className="text-xl font-semibold">Amina Stays</p>
          <p className="text-sm text-white/60">Voice line · English / Kiswahili</p>
        </div>
        <button onClick={() => start("Inbound")} aria-label="Call Amina Stays" className="grid size-16 place-items-center rounded-full bg-success shadow-lg transition hover:scale-105"><Phone className="size-7" /></button>
        {isHost && (
          <button onClick={() => start("Outbound")} className="flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-xs font-semibold hover:bg-white/20">
            <PhoneIncoming className="size-4" /> Answer the SOS safety call
          </button>
        )}
        {isHost && (
          <button onClick={() => start("Outbound", "bridge-latest")} className="flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-xs font-semibold hover:bg-white/20">
            <PhoneIncoming className="size-4" /> Answer a support call-back
          </button>
        )}
        <button onClick={() => setSpeakOn(!speakOn)} className="flex items-center gap-2 text-xs text-white/60">
          {speakOn ? <Volume2 className="size-4" /> : <VolumeX className="size-4" />} Speak aloud {speakOn ? "on" : "off"}
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-gradient-to-b from-[#16202a] to-[#0b1016] text-white">
      <div className="px-4 pt-2 text-center">
        <p className="text-sm font-semibold">Amina Stays</p>
        <p className="text-xs text-white/60 tabular-nums">{state === "ended" ? "Ended" : `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`}</p>
      </div>
      <div ref={list} className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 py-3">
        {lines.map((l, i) => (
          <p key={i} className={cn("rounded-xl px-3 py-2 text-[12.5px] leading-snug", l.who === "ivr" ? "bg-white/10" : l.who === "me" ? "ml-auto w-fit bg-success/80" : "text-center text-[11px] text-white/50")}>{l.text}</p>
        ))}
      </div>
      {state === "dial" ? (
        <div className="space-y-2 p-4">
          <p className="text-center text-xs text-white/70">Bridging to {dialTo}. Did they pick up?</p>
          <div className="grid grid-cols-2 gap-2">
            <button className="rounded-xl bg-success py-2 text-xs font-semibold" onClick={() => finish(call.current.id, { dialDuration: "75" })}>They answered</button>
            <button className="rounded-xl bg-white/10 py-2 text-xs font-semibold" onClick={() => finish(call.current.id, { dialDuration: "0" })}>No answer</button>
          </div>
        </div>
      ) : state === "record" ? (
        <div className="flex flex-col items-center gap-3 p-5">
          <span className="flex items-center gap-2 text-sm text-danger"><Mic className="size-4 animate-pulse" /> Recording…</span>
          <button className="rounded-full bg-white/10 px-4 py-2 text-xs font-semibold" onClick={() => press("#")}>Finish message (#)</button>
        </div>
      ) : state !== "ended" ? (
        <div className="px-6 pb-2">
          <p className="h-6 text-center font-mono text-lg tracking-widest">{buffer}</p>
          <div className="grid grid-cols-3 gap-2">
            {["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"].map((k) => (
              <button key={k} onClick={() => press(k)} disabled={state !== "digits"} className="h-11 rounded-full bg-white/10 text-lg font-semibold transition enabled:hover:bg-white/20 disabled:opacity-30">{k}</button>
            ))}
          </div>
        </div>
      ) : null}
      <div className="flex items-center justify-center gap-6 p-4">
        {state === "ended" ? (
          <button onClick={() => setState("idle")} className="flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-xs font-semibold"><RotateCcw className="size-4" /> New call</button>
        ) : (
          <>
            <button onClick={() => setSpeakOn(!speakOn)} aria-label="Toggle speech" className="grid size-11 place-items-center rounded-full bg-white/10">{speakOn ? <Volume2 className="size-5" /> : <VolumeX className="size-5" />}</button>
            <button onClick={hangup} aria-label="Hang up" className="grid size-14 place-items-center rounded-full bg-danger"><PhoneOff className="size-6" /></button>
            <button onClick={() => { bufRef.current = bufRef.current.slice(0, -1); setBuffer(bufRef.current); }} disabled={state !== "digits"} aria-label="Delete digit" className="grid size-11 place-items-center rounded-full bg-white/10 disabled:opacity-30"><Delete className="size-5" /></button>
          </>
        )}
      </div>
    </div>
  );
}

// ---------- Time machine ----------

const STEPS: { step: string; label: string; when: string }[] = [
  { step: "pre_arrival", label: "Pre-arrival check-in", when: "3 days before" },
  { step: "id_request", label: "Ask for ID (guest register)", when: "2 days before" },
  { step: "directions", label: "Directions & Wi-Fi", when: "Day before" },
  { step: "code", label: "Release door code", when: "Arrival, 8:00" },
  { step: "welcome_check", label: "“All good?” check", when: "Arrival evening" },
  { step: "mid_stay", label: "Mid-stay clean offer", when: "Day 3" },
  { step: "checkout_reminder", label: "Checkout reminder", when: "Last evening" },
  { step: "checkout", label: "Check out", when: "Departure" },
  { step: "review", label: "Ask for a review", when: "After the stay" },
];
const CODE_RESULT: Record<string, string> = {
  released: "door code released and sent by SMS",
  not_confirmed: "code not released: the booking isn't confirmed",
  waiting_balance: "code held: the balance isn't paid yet",
  waiting_id: "code held: the guest register (ID) is missing",
  checking_sim: "code held: SIM-swap check in progress",
  security_hold: "code held: recent SIM swap detected, Amina must verify",
  too_early: "code not released: it's not check-in day yet",
};

function TimeMachine({ guests }: { guests: DemoPersona[] }) {
  const qc = useQueryClient();
  const { mpesa } = usePayOptions();
  const withRef = guests.filter((g) => g.ref);
  const [ref, setRef] = React.useState(withRef[0]?.ref ?? "");
  const [busy, setBusy] = React.useState<string | null>(null);
  const [log, setLog] = React.useState<{ at: string; text: string; ok: boolean }[]>([]);

  async function act(key: string, fn: () => Promise<string>) {
    setBusy(key);
    try {
      const text = await fn();
      setLog((l) => [{ at: new Date().toLocaleTimeString(), text, ok: true }, ...l].slice(0, 8));
      qc.invalidateQueries();
    } catch (e) {
      setLog((l) => [{ at: new Date().toLocaleTimeString(), text: (e as Error).message, ok: false }, ...l].slice(0, 8));
    } finally {
      setBusy(null);
    }
  }
  const advance = (step: string, force = false) =>
    act(step, async () => {
      const r = await post<{ ref: string; status: string; result: string }>(`/api/demo/advance/${ref}`, { step, force });
      const what = step === "code" ? CODE_RESULT[r.result] ?? r.result : `${STEPS.find((s) => s.step === step)?.label} sent`;
      return `${r.ref}: ${what} · now ${r.status.replace("_", " ")}`;
    });

  return (
    <section className="min-w-0">
      <h2 className="flex items-center gap-2 text-[22px] font-bold tracking-tight"><CalendarClock className="size-6" /> Time machine</h2>
      <p className="mt-1 text-ink-2">Fast-forward a stay through every automated message — exactly what the scheduler sends on the real dates. Hold that guest&apos;s phone above to watch them arrive.</p>
      <div className="mt-5 rounded-2xl border border-line-soft p-5">
        <div className="flex flex-wrap items-center gap-3">
          <Select value={ref} onChange={(e) => setRef(e.target.value)} className="h-11 max-w-sm" aria-label="Booking">
            {withRef.map((g) => <option key={g.ref} value={g.ref!}>{g.ref} · {g.name} · {g.note}</option>)}
          </Select>
          <Button variant="brand" loading={busy === "pay"} disabled={!ref} onClick={() => act("pay", async () => {
            const r = await post<{ ref: string; status: string; paid: number }>(`/api/demo/pay/${ref}`);
            return `${r.ref}: payment simulated · paid KES ${r.paid.toLocaleString()} · ${r.status.replace("_", " ")}`;
          })}>
            <Smartphone className="size-4" /> Simulate payment
          </Button>
        </div>
        <ol className="mt-5 grid gap-2 sm:grid-cols-2">
          {STEPS.map((s, i) => (
            <li key={s.step}>
              <button onClick={() => advance(s.step)} disabled={!!busy || !ref} className="flex w-full items-center gap-3 rounded-xl border border-line-soft px-3 py-2.5 text-left transition hover:border-ink disabled:opacity-50">
                <span className="grid size-7 shrink-0 place-items-center rounded-full bg-surface text-xs font-bold">{busy === s.step ? "…" : i + 1}</span>
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold">{s.label}</span>
                  <span className="block text-xs text-ink-2">{s.when}</span>
                </span>
              </button>
            </li>
          ))}
        </ol>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="soft" size="sm" onClick={() => advance("code", true)} disabled={!!busy || !ref}>Force-release code (host override)</Button>
          {mpesa && (
            <>
              <Button variant="soft" size="sm" loading={busy === "c2b"} disabled={!!busy || !ref} onClick={() => act("c2b", async () => {
                const r = await post<{ trans_id: string; matched: boolean }>("/api/demo/c2b", { ref });
                return `${ref}: Paybill payment ${r.trans_id} ${r.matched ? "received and matched to the booking" : "received — unmatched, see Host › Payments"}`;
              })}><Landmark className="size-4" /> Simulate Paybill payment</Button>
              <Button variant="soft" size="sm" loading={busy === "fail"} disabled={!!busy || !ref} onClick={() => act("fail", async () => {
                const r = await post<{ ok: boolean; status: string; failure_code?: string }>(`/api/demo/pay/${ref}`, { result: 1032 });
                return `${ref}: M-Pesa prompt cancelled on the phone (code ${r.failure_code ?? 1032}) · ${r.status.replace("_", " ")}`;
              })}>Simulate “cancelled on phone”</Button>
            </>
          )}
          <Button variant="soft" size="sm" loading={busy === "outage"} disabled={!!busy || !ref} onClick={() => act("outage", async () => {
            const r = await post<{ notice: number; told: number; data_mb: number }>(`/api/demo/outage/${ref}`, { service: "wifi" });
            return `${ref}: Wi-Fi outage #${r.notice} posted · ${r.told} guest(s) texted${r.data_mb ? ` · ${r.data_mb} MB data bundle to anyone staying` : ""}`;
          })}><WifiOff className="size-4" /> Wi-Fi outage at this home</Button>
          <Button variant="soft" size="sm" loading={busy === "restore"} disabled={!!busy || !ref} onClick={() => act("restore", async () => {
            const r = await post<{ notice: number; told: number }>(`/api/demo/outage/${ref}`, { restore: true });
            return `${ref}: alert #${r.notice} resolved · ${r.told} guest(s) told it's fixed`;
          })}>Fix it</Button>
          <Button variant="soft" size="sm" loading={busy === "tick"} onClick={() => act("tick", async () => {
            const r = await post<Record<string, unknown>>("/api/demo/tick", {});
            const keys = Object.keys(r);
            return keys.length ? `Scheduler ran: ${keys.map((k) => `${k}=${JSON.stringify(r[k])}`).join(", ").slice(0, 220)}` : "Scheduler: nothing due right now";
          })}><Zap className="size-4" /> Run due jobs now</Button>
        </div>
        {log.length > 0 && (
          <ul className="mt-5 space-y-1.5 border-t border-line-soft pt-4 text-sm">
            {log.map((l, i) => (
              <li key={i} className={cn("flex gap-2", !l.ok && "text-danger")}><CheckCheck className={cn("mt-0.5 size-4 shrink-0", l.ok ? "text-success" : "text-danger")} /><span><span className="text-ink-2">{l.at}</span> · {l.text}</span></li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function ResetButton() {
  const [busy, setBusy] = React.useState(false);
  return (
    <Dialog>
      <DialogTrigger asChild><Button variant="soft"><RotateCcw className="size-4" /> Reset demo data</Button></DialogTrigger>
      <DialogContent title="Reset the demo?" size="sm">
        <div className="space-y-4 p-6">
          <p className="text-[15px] text-ink-2">This re-seeds the homes, guests, bookings and messages to the starting story and logs everyone out. Takes a few seconds.</p>
          <DialogClose asChild>
            <Button variant="danger" size="lg" className="w-full" loading={busy} onClick={async () => {
              setBusy(true);
              try {
                await post("/api/demo/reset");
                toast.success("Demo reset");
                window.location.reload();
              } catch (e) {
                toast.error((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}>Reset everything</Button>
          </DialogClose>
        </div>
      </DialogContent>
    </Dialog>
  );
}
