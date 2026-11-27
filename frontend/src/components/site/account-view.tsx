"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, Download, Globe, LogOut, Megaphone, ShieldCheck, Trash2, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { useLogout, useMe } from "@/components/providers";
import { AuthGate } from "@/components/site/auth-gate";
import { SiteHeader } from "@/components/site/header";
import { Photo } from "@/components/site/listing-card";
import { RewardsSection } from "@/components/site/rewards-section";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/input";
import { Icon3D, type Icon3DName } from "@/components/ui/icon3d";
import { Avatar, Badge } from "@/components/ui/misc";
import { Switch } from "@/components/ui/overlays";
import { del, get, patch, post } from "@/lib/api";
import { fmtDate, fmtRange } from "@/lib/format";
import type { Me, WaitlistEntry } from "@/lib/types";
import { COUNTRIES } from "@/lib/utils";

const ACCOUNT_CARDS: { icon: Icon3DName; title: string; text: string; href: string }[] = [
  { icon: "guests", title: "Personal info", text: "Your name, email, language and how we reach you", href: "#personal" },
  { icon: "clipboard", title: "Guest register ID", text: "The ID Kenyan law asks every host to record — stored encrypted", href: "#identity" },
  { icon: "envelope", title: "Notifications", text: "Booking messages always come; offers only if you say so", href: "#notifications" },
  { icon: "lock", title: "Privacy & your data", text: "Download or erase your data under the Data Protection Act", href: "#data" },
  { icon: "homes", title: "Trips", text: "Bookings from the web, USSD, SMS and calls", href: "/trips" },
  { icon: "trophy", title: "Rewards", text: "Points for every stay, swapped for airtime or data", href: "#rewards" },
  { icon: "speech-balloon", title: "Support requests", text: "Complaints and call-backs, each with a reference", href: "/help#support" },
  { icon: "palm-tree", title: "Local guide", text: "What to see, eat and do near your home", href: "/guide" },
  { icon: "mobile-phone", title: "Book without data", text: "USSD, SMS and voice — the same account", href: "/help#book-your-way" },
];

export function AccountView() {
  return (
    <AuthGate title="Log in to your account">
      <Account />
    </AuthGate>
  );
}

function Account() {
  const qc = useQueryClient();
  const router = useRouter();
  const logout = useLogout();
  const { data: me } = useMe();
  const [form, setForm] = React.useState({ name: me?.name ?? "", email: me?.email ?? "", lang: me?.lang ?? "en", nationality: me?.nationality ?? "", preferred_channel: me?.preferred_channel ?? "sms" });
  const [saving, setSaving] = React.useState(false);
  const [id, setId] = React.useState({ id_type: "passport", id_number: "", consent: false });
  const [confirm, setConfirm] = React.useState("");
  if (!me) return null;

  async function save(body: Partial<Me> | typeof form, msg = "Saved") {
    setSaving(true);
    try {
      qc.setQueryData(["me"], await patch<Me>("/api/me", body));
      toast.success(msg);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function exportData() {
    try {
      const data = await get<unknown>("/api/me/export");
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const a = Object.assign(document.createElement("a"), { href: url, download: "amina-stays-my-data.json" });
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  async function erase() {
    try {
      const r = await post<{ erased: boolean; register_kept: boolean }>("/api/me/erase");
      toast.success(r.register_kept ? "Done. Only the legally required guest-register entry remains." : "Your personal data has been erased.");
      await qc.invalidateQueries();
      router.push("/");
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <>
      <SiteHeader />
      <main className="container-narrow max-w-[1080px] pt-10 pb-24">
        <h1 className="text-[32px] leading-tight font-semibold tracking-tight">Account</h1>
        <div className="mt-3 flex items-center gap-4">
          <Avatar name={me.name || me.phone} size={48} className="bg-ink!" />
          <p className="text-lg"><b className="font-semibold">{me.name || "Your account"}</b><span className="text-ink-2">, {me.phone} · your phone number is your login everywhere</span></p>
        </div>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {ACCOUNT_CARDS.map((c) => (
            <Link key={c.title} href={c.href} className="rounded-2xl p-5 shadow-[0_6px_16px_rgb(0_0_0/0.12)] transition-shadow hover:shadow-[0_8px_28px_rgb(0_0_0/0.18)]">
              <Icon3D name={c.icon} size={36} />
              <p className="mt-6 font-semibold">{c.title}</p>
              <p className="mt-1 text-sm text-ink-2">{c.text}</p>
            </Link>
          ))}
        </div>

        <section id="personal" className="mt-16 scroll-mt-24 border-t border-line-soft pt-10">
          <h2 className="flex items-center gap-2 text-[22px] font-bold"><UserRound className="size-5" /> Personal info</h2>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <Field label="Name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Email"><Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label="Messages in">
              <Select value={form.lang} onChange={(e) => setForm({ ...form, lang: e.target.value as Me["lang"] & string })}>
                {(me.languages ?? [["en", "English"]]).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            </Field>
            <Field label="Nationality">
              <Select value={form.nationality} onChange={(e) => setForm({ ...form, nationality: e.target.value })}>
                <option value="">Select…</option>
                {COUNTRIES.map(([c, n]) => <option key={c} value={c}>{n}</option>)}
              </Select>
            </Field>
            <Field label="Updates by" hint="WhatsApp needs a WhatsApp number on this phone">
              <Select value={form.preferred_channel} onChange={(e) => setForm({ ...form, preferred_channel: e.target.value as "sms" | "whatsapp" })}>
                <option value="sms">SMS</option><option value="whatsapp">WhatsApp</option>
              </Select>
            </Field>
          </div>
          <Button className="mt-5" onClick={() => save(form)} loading={saving}>Save changes</Button>
        </section>

        <section id="identity" className="mt-12 scroll-mt-24 border-t border-line-soft pt-10">
          <h2 className="flex items-center gap-2 text-[22px] font-bold"><ShieldCheck className="size-5" /> Identity for the guest register</h2>
          {me.identity?.last4 ? (
            <div className="mt-4 flex flex-wrap items-center gap-3 rounded-2xl border border-line-soft p-5">
              <Badge tone="success">On file</Badge>
              <span className="font-semibold">{me.identity.type_label} {me.identity.last4}</span>
              <span className="text-sm text-ink-2">added {fmtDate(me.identity.submitted_at, "d MMM yyyy")} · stored encrypted</span>
            </div>
          ) : (
            <p className="mt-2 text-ink-2">Not added yet. Kenyan law requires a guest register — add it once and every future stay is ready.</p>
          )}
          <div className="mt-5 grid gap-4 sm:grid-cols-3">
            <Field label="Document">
              <Select value={id.id_type} onChange={(e) => setId({ ...id, id_type: e.target.value })}>
                {(me.id_types ?? []).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            </Field>
            <Field label={me.identity?.last4 ? "Replace with number" : "Number"} className="sm:col-span-2"><Input value={id.id_number} onChange={(e) => setId({ ...id, id_number: e.target.value })} /></Field>
          </div>
          <label className="mt-4 flex items-start gap-3 text-sm">
            <input type="checkbox" className="mt-0.5 size-4 accent-ink" checked={id.consent} onChange={(e) => setId({ ...id, consent: e.target.checked })} />
            <span>I agree to my ID number being stored encrypted for the guest register, as explained in the <Link href="/privacy" className="underline">privacy notice</Link>.</span>
          </label>
          <Button className="mt-4" variant="soft" disabled={!id.id_number || !id.consent} onClick={async () => {
            try {
              qc.setQueryData(["me"], await post<Me>("/api/me/identity", { ...id, nationality: form.nationality }));
              setId({ ...id, id_number: "" });
              toast.success("ID saved securely");
            } catch (e) {
              toast.error((e as Error).message);
            }
          }}>Save ID</Button>
        </section>

        <section id="notifications" className="mt-12 scroll-mt-24 border-t border-line-soft pt-10">
          <h2 className="flex items-center gap-2 text-[22px] font-bold"><Megaphone className="size-5" /> Notifications</h2>
          <div className="mt-5 flex items-start justify-between gap-6 rounded-2xl border border-line-soft p-5">
            <div>
              <p className="font-semibold">Offers &amp; seasonal deals</p>
              <p className="text-sm text-ink-2">Occasional SMS, never after 6pm. Reply STOP to any message to opt out. Booking messages (confirmations, codes, receipts) always come through.</p>
            </div>
            <Switch checked={!!me.marketing_opt_in} onCheckedChange={(v) => save({ marketing_opt_in: v }, v ? "You'll get our offers" : "Unsubscribed from offers")} aria-label="Offers by SMS" />
          </div>
        </section>

        <RewardsSection />

        <WaitlistSection />

        <section id="data" className="mt-12 scroll-mt-24 border-t border-line-soft pt-10">
          <h2 className="flex items-center gap-2 text-[22px] font-bold"><Globe className="size-5" /> Your data</h2>
          <p className="mt-2 text-ink-2">Your rights under Kenya&apos;s Data Protection Act, 2019. Read the <Link href="/privacy" className="underline">privacy notice</Link>.</p>
          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            <button onClick={exportData} className="flex items-start gap-4 rounded-2xl border border-line-soft p-5 text-left hover:border-ink">
              <Download className="mt-0.5 size-5" />
              <span><b className="block">Download my data</b><span className="text-sm text-ink-2">Bookings, messages and profile as a JSON file</span></span>
            </button>
            <Dialog>
              <DialogTrigger asChild>
                <button className="flex items-start gap-4 rounded-2xl border border-line-soft p-5 text-left hover:border-danger">
                  <Trash2 className="mt-0.5 size-5 text-danger" />
                  <span><b className="block">Erase my data</b><span className="text-sm text-ink-2">Remove your personal information</span></span>
                </button>
              </DialogTrigger>
              <DialogContent title="Erase your personal data?" size="sm">
                <div className="space-y-4 p-6 text-[15px]">
                  <p className="text-ink-2">We&apos;ll delete your email, preferences, wishlist and message history, stop all offers and log you out. Any upcoming booking stays valid and its essential messages (door code, receipts) still reach you.</p>
                  <p className="text-ink-2">If you&apos;ve stayed with us, your name, ID and stay dates remain in the guest register for the 5 years Kenyan tourism law requires, then are erased automatically; financial records are kept for KRA.</p>
                  <Field label='Type "ERASE" to confirm'><Input value={confirm} onChange={(e) => setConfirm(e.target.value)} /></Field>
                  <Button variant="danger" size="lg" className="w-full" disabled={confirm !== "ERASE"} onClick={erase}>Erase my data</Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>
        </section>

        <Button variant="ghost" className="mt-12" onClick={logout}><LogOut className="size-4" /> Log out</Button>
      </main>
    </>
  );
}

/** Dates the guest asked to be told about. Hidden until there is at least one. */
function WaitlistSection() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["waitlist"], queryFn: () => get<WaitlistEntry[]>("/api/me/waitlist") });
  if (!data?.length) return null;
  async function leave(id: number) {
    try {
      await del(`/api/me/waitlist/${id}`);
      qc.setQueryData<WaitlistEntry[]>(["waitlist"], (old) => old?.filter((w) => w.id !== id));
      toast.success("Removed from the waitlist");
    } catch (e) {
      toast.error((e as Error).message);
    }
  }
  return (
    <section id="waitlist" className="mt-12 scroll-mt-24 border-t border-line-soft pt-10">
      <h2 className="flex items-center gap-2 text-[22px] font-bold"><BellRing className="size-5" /> Waitlist</h2>
      <p className="mt-2 text-ink-2">We text you the moment one of these opens up — first come, first served.</p>
      <ul className="mt-5 space-y-3">
        {data.map((w) => (
          <li key={w.id} className="flex flex-wrap items-center gap-4 rounded-2xl border border-line-soft p-4">
            {w.unit?.photo && <Photo src={w.unit.photo} alt="" sizes="56px" className="size-14 shrink-0 rounded-xl object-cover" />}
            <div className="min-w-0 flex-1">
              <p className="font-semibold">{w.unit?.name ?? `Any home in ${w.area?.name ?? "Mombasa"}`}</p>
              <p className="text-sm text-ink-2">{fmtRange(w.check_in, w.check_out)} · {w.guests} guest{w.guests === 1 ? "" : "s"}</p>
            </div>
            {w.status === "offered" && w.book_url ? (
              <Button asChild size="sm" variant="brand"><Link href={w.book_url}>It&apos;s free — book now</Link></Button>
            ) : (
              <Badge tone="neutral">Waiting</Badge>
            )}
            <Button size="sm" variant="ghost" onClick={() => leave(w.id)}>Leave</Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
