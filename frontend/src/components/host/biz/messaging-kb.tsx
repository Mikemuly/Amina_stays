"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, MessageCircleQuestion, Pencil, Plus, Search, Send, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ErrorBlock, LoadingBlock } from "@/components/host/common";
import { usePayOptions } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input, Select, Textarea } from "@/components/ui/input";
import { Badge, EmptyState } from "@/components/ui/misc";
import { Switch } from "@/components/ui/overlays";
import { del, get, patch, post } from "@/lib/api";
import { plural } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useHostSettings, useInvalidateHost, useListings } from "./queries";
import type { Faq, FaqTestResult } from "./types";
import { Callout, ConfirmDialog, Field, IconButton, errorMessage, fieldErrors, humanize } from "./ui";

const CATEGORIES = ["booking", "pricing", "check_in", "breakfast", "wifi", "amenities", "transport", "area", "safety", "payment", "policies", "other"];
const CATEGORY_LABEL: Record<string, string> = { check_in: "Check-in", wifi: "Wi-Fi" };
const catLabel = (c: string) => CATEGORY_LABEL[c] ?? humanize(c);

const ANSWER_LANGS = [
  { key: "answer_en", label: "English", code: "en" },
  { key: "answer_sw", label: "Kiswahili", code: "sw" },
  { key: "answer_fr", label: "Français", code: "fr" },
  { key: "answer_de", label: "Deutsch", code: "de" },
] as const;
type AnswerKey = (typeof ANSWER_LANGS)[number]["key"];

const PUBLIC_FACTS = ["checkin_time", "checkout_time", "prices", "deposit_percent", "ussd_code", "sms_number", "website", "business", "host"];
const BOOKED_FACTS = ["wifi", "directions", "landmark", "map_link", "address", "parking", "unit", "ref", "check_in", "check_out", "code"];

const examples = (mpesa: boolean) => ["What time is check-in?", "Is breakfast included?", "How do I get from the airport?", mpesa ? "Can I pay with M-Pesa?" : "Can I pay by card?", "Kuna maegesho?", "What's the Wi-Fi password?"];

function Highlighted({ text }: { text: string }) {
  const parts = text.split(/(\{\w+\})/g);
  return (
    <>
      {parts.map((p, i) =>
        /^\{\w+\}$/.test(p) ? (
          <span key={i} className={cn("rounded px-1 font-mono text-[0.92em]", BOOKED_FACTS.includes(p.slice(1, -1)) ? "bg-brand-50 text-brand-700" : "bg-ocean-50 text-ocean-700")}>
            {p}
          </span>
        ) : (
          <React.Fragment key={i}>{p}</React.Fragment>
        ),
      )}
    </>
  );
}

export function KnowledgeTab() {
  const invalidate = useInvalidateHost();
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["host", "faqs"], queryFn: () => get<Faq[]>("/api/host/faqs") });
  const { data: settings } = useHostSettings();
  const { data: listings } = useListings();
  const [q, setQ] = React.useState("");
  const [cat, setCat] = React.useState("all");
  const [editing, setEditing] = React.useState<Faq | "new" | null>(null);
  const [toDelete, setToDelete] = React.useState<Faq | null>(null);

  const toggle = useMutation({
    mutationFn: (f: Faq) => patch<Faq>(`/api/host/faqs/${f.id}`, { active: !f.active }),
    onSuccess: (f) => {
      toast.success(f.active ? "Answer switched on" : "Answer switched off — questions like it go to your inbox");
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (f: Faq) => del(`/api/host/faqs/${f.id}`),
    onSuccess: () => {
      toast.success("Answer deleted");
      setToDelete(null);
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const faqs = data ?? [];
  const needle = q.trim().toLowerCase();
  const shown = faqs.filter(
    (f) => (cat === "all" || f.category === cat) && (!needle || [f.question, f.answer_en, f.keywords].some((x) => x.toLowerCase().includes(needle))),
  );
  const cats = CATEGORIES.filter((c) => shown.some((f) => f.category === c)).concat(
    [...new Set(shown.map((f) => f.category))].filter((c) => !CATEGORIES.includes(c)),
  );
  const totalHits = faqs.reduce((s, f) => s + f.hits, 0);
  const unitName = (id: number | null) => listings?.find((l) => l.id === id)?.name;

  return (
    <div className="space-y-6">
      <TryIt />

      <div className="grid gap-4 lg:grid-cols-2">
        <Callout tone="info" title="Placeholders keep answers true">
          Write <Highlighted text="{checkin_time}" />, <Highlighted text="{prices}" /> or <Highlighted text="{deposit_percent}" /> and the live value from your
          settings and listings is filled in — change a price once and every answer updates.
        </Callout>
        <Callout tone="trust" title="Private facts only reach booked guests">
          Answers using <Highlighted text="{wifi}" />, <Highlighted text="{directions}" /> or <Highlighted text="{code}" /> are only sent to a guest with a confirmed
          booking. Anyone else gets a public answer or is passed to you.
        </Callout>
      </div>

      <section className="rounded-2xl border border-line-soft bg-white">
        <header className="flex flex-wrap items-center gap-3 border-b border-line-soft px-5 py-4">
          <div className="mr-auto">
            <h2 className="text-[15px] font-bold">Answers</h2>
            <p className="text-[13px] text-ink-2">
              {plural(faqs.filter((f) => f.active).length, "active answer")} · used {plural(totalHits, "time")}
              {settings && !settings.auto_answer && <span className="font-semibold text-warning"> · auto-answer is off in Settings</span>}
            </p>
          </div>
          <div className="relative w-full sm:w-56">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search answers" aria-label="Search answers" className="h-9 pl-9 text-sm" />
          </div>
          <Select value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Category" className="h-9 w-40 text-sm">
            <option value="all">All topics</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {catLabel(c)}
              </option>
            ))}
          </Select>
          <Button variant="dark" size="sm" className="h-9" onClick={() => setEditing("new")}>
            <Plus className="size-4" /> New answer
          </Button>
        </header>

        {error ? (
          <div className="p-5">
            <ErrorBlock error={error} retry={refetch} />
          </div>
        ) : isLoading ? (
          <div className="p-5">
            <LoadingBlock rows={5} />
          </div>
        ) : shown.length === 0 ? (
          <div className="p-5">
            <EmptyState icon={<MessageCircleQuestion className="size-5" />} title={faqs.length ? "No answers match" : "No answers yet"}>
              {faqs.length ? "Try another search or topic." : "Add the questions guests ask most — Ask Amina answers them instantly by SMS, USSD and on the website."}
            </EmptyState>
          </div>
        ) : (
          <div className="divide-y divide-line-soft">
            {cats.map((c) => {
              const items = shown.filter((f) => f.category === c);
              return (
                <div key={c}>
                  <div className="flex items-baseline justify-between bg-surface/60 px-5 py-2">
                    <h3 className="text-[12px] font-bold tracking-wider text-ink-2 uppercase">{catLabel(c)}</h3>
                    <span className="text-[12px] text-ink-3 tabular-nums">
                      {items.length} · {plural(items.reduce((s, f) => s + f.hits, 0), "hit")}
                    </span>
                  </div>
                  <ul className="divide-y divide-line-soft">
                    {items.map((f) => (
                      <li key={f.id} className={cn("flex gap-4 px-5 py-4", !f.active && "opacity-60")}>
                        <div className="min-w-0 flex-1">
                          <p className="flex flex-wrap items-center gap-2 text-[15px] font-semibold">
                            {f.question}
                            {f.unit && <Badge tone="brand">{unitName(f.unit) ?? `Home #${f.unit}`}</Badge>}
                          </p>
                          <p className="mt-1 line-clamp-2 text-[13.5px] leading-relaxed text-ink-2">
                            <Highlighted text={f.answer_en} />
                          </p>
                          <div className="mt-2 flex flex-wrap items-center gap-1.5">
                            {ANSWER_LANGS.map((l) => (
                              <span
                                key={l.code}
                                title={f[l.key] ? `${l.label} answer` : `No ${l.label} answer — English is used`}
                                className={cn("rounded px-1.5 py-0.5 text-[10.5px] font-bold uppercase", f[l.key] ? "bg-ink text-white" : "bg-surface text-ink-3")}
                              >
                                {l.code}
                              </span>
                            ))}
                            <span className="mx-1 text-ink-3">·</span>
                            {f.keywords
                              .split(",")
                              .map((k) => k.trim())
                              .filter(Boolean)
                              .slice(0, 4)
                              .map((k) => (
                                <span key={k} className="rounded-full border border-line-soft px-2 py-0.5 text-[11.5px] text-ink-2">
                                  {k}
                                </span>
                              ))}
                          </div>
                        </div>
                        <div className="flex shrink-0 flex-col items-end gap-2">
                          <span className="text-[12.5px] font-semibold text-ink-2 tabular-nums">{plural(f.hits, "hit")}</span>
                          <div className="flex items-center gap-1">
                            <Switch checked={f.active} onCheckedChange={() => toggle.mutate(f)} aria-label={`${f.question}: ${f.active ? "active" : "off"}`} />
                            <IconButton label="Edit answer" onClick={() => setEditing(f)}>
                              <Pencil />
                            </IconButton>
                            <IconButton label="Delete answer" tone="danger" onClick={() => setToDelete(f)}>
                              <Trash2 />
                            </IconButton>
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </section>

      <Dialog open={editing !== null} onOpenChange={(v) => !v && setEditing(null)}>
        {editing !== null && <FaqEditor faq={editing === "new" ? null : editing} onDone={() => setEditing(null)} />}
      </Dialog>

      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(v) => !v && setToDelete(null)}
        title="Delete this answer?"
        confirmLabel="Delete"
        tone="danger"
        loading={remove.isPending}
        onConfirm={() => toDelete && remove.mutate(toDelete)}
      >
        “{toDelete?.question}” — guests asking this will be passed to your inbox instead. Tip: switch it off to keep the text.
      </ConfirmDialog>
    </div>
  );
}

function TryIt() {
  const { mpesa } = usePayOptions();
  const [text, setText] = React.useState("");
  const [lang, setLang] = React.useState("en");
  const [asked, setAsked] = React.useState<string | null>(null);
  const test = useMutation({ mutationFn: (body: { text: string; lang: string }) => post<FaqTestResult>("/api/host/faq-test", body) });
  const ask = (t = text) => {
    if (!t.trim()) return;
    setText(t);
    setAsked(t.trim());
    test.mutate({ text: t.trim(), lang });
  };
  return (
    <section className="overflow-hidden rounded-2xl border border-ocean-100 bg-gradient-to-br from-ocean-50 via-white to-white">
      <div className="grid gap-6 p-5 sm:p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div>
          <p className="flex items-center gap-2 text-[13px] font-bold tracking-wide text-ocean-700 uppercase">
            <Bot className="size-4" /> Try Ask Amina
          </p>
          <h2 className="mt-1 text-xl font-bold tracking-tight">Type a guest question</h2>
          <p className="mt-1 text-[14px] text-ink-2">See exactly what an SMS, USSD or website guest without a booking would get back — instantly, any hour.</p>
          <form
            className="mt-4 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              ask();
            }}
          >
            <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. Do you have parking?" aria-label="Guest question" className="bg-white" />
            <Select value={lang} onChange={(e) => setLang(e.target.value)} aria-label="Answer language" className="w-24 bg-white">
              {ANSWER_LANGS.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.code.toUpperCase()}
                </option>
              ))}
            </Select>
            <Button type="submit" variant="ocean" className="h-11" loading={test.isPending} aria-label="Ask">
              {!test.isPending && <Send className="size-4" />}
            </Button>
          </form>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {examples(mpesa).map((ex) => (
              <button key={ex} type="button" onClick={() => ask(ex)} className="rounded-full border border-line bg-white px-3 py-1 text-[12.5px] font-medium text-ink-2 transition hover:border-ink-3 hover:text-ink">
                {ex}
              </button>
            ))}
          </div>
        </div>

        <div className="flex min-h-48 flex-col justify-end gap-2.5 rounded-2xl bg-[#f2f2f7] p-4" aria-live="polite">
          {!asked ? (
            <p className="m-auto max-w-64 text-center text-[13.5px] text-ink-3">The conversation appears here, as it would on the guest&apos;s phone.</p>
          ) : (
            <>
              <div className="ml-auto max-w-[85%] rounded-[1.1rem] rounded-br-[0.35rem] bg-ocean-600 px-3.5 py-2 text-[14px] text-white">{asked}</div>
              {test.isPending ? (
                <div className="max-w-[85%] rounded-[1.1rem] rounded-bl-[0.35rem] bg-white px-4 py-3 text-ink-3">…</div>
              ) : test.error ? (
                <p className="text-[13px] text-danger">{errorMessage(test.error)}</p>
              ) : test.data?.matched ? (
                <>
                  <div className="max-w-[85%] rounded-[1.1rem] rounded-bl-[0.35rem] bg-white px-3.5 py-2 text-[14px] leading-snug whitespace-pre-wrap text-ink shadow-sm">
                    {test.data.answer}
                  </div>
                  <p className="text-[12px] text-ink-2">
                    Matched <b className="text-ink">“{test.data.question}”</b> · answered automatically
                  </p>
                </>
              ) : (
                <>
                  <div className="max-w-[85%] rounded-[1.1rem] rounded-bl-[0.35rem] bg-white px-3.5 py-2 text-[14px] text-ink shadow-sm">
                    Asante! I&apos;ve passed your question to Amina — she&apos;ll reply shortly.
                  </div>
                  <p className="text-[12px] text-ink-2">
                    <b className="text-warning">No confident match</b> — this lands in your inbox as “needs reply”. Add keywords to an answer to catch it next time.
                  </p>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}

type FaqDraft = Pick<Faq, "category" | "question" | "answer_en" | "answer_sw" | "answer_fr" | "answer_de" | "keywords" | "unit" | "active">;

function FaqEditor({ faq, onDone }: { faq: Faq | null; onDone: () => void }) {
  const invalidate = useInvalidateHost();
  const { data: listings } = useListings();
  const [d, setD] = React.useState<FaqDraft>(() =>
    faq
      ? { category: faq.category, question: faq.question, answer_en: faq.answer_en, answer_sw: faq.answer_sw, answer_fr: faq.answer_fr, answer_de: faq.answer_de, keywords: faq.keywords, unit: faq.unit, active: faq.active }
      : { category: "booking", question: "", answer_en: "", answer_sw: "", answer_fr: "", answer_de: "", keywords: "", unit: null, active: true },
  );
  const [lang, setLang] = React.useState<AnswerKey>("answer_en");
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [saving, setSaving] = React.useState(false);
  const ref = React.useRef<HTMLTextAreaElement>(null);
  const keywords = d.keywords.split(",").map((k) => k.trim()).filter(Boolean);

  const insert = (ph: string) => {
    const token = `{${ph}}`;
    const el = ref.current;
    const cur = d[lang];
    const start = el?.selectionStart ?? cur.length;
    const end = el?.selectionEnd ?? cur.length;
    setD({ ...d, [lang]: cur.slice(0, start) + token + cur.slice(end) });
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(start + token.length, start + token.length);
    });
  };

  const save = async () => {
    setSaving(true);
    setErrors({});
    try {
      if (faq) await patch(`/api/host/faqs/${faq.id}`, d);
      else await post("/api/host/faqs", d);
      toast.success(faq ? "Answer updated" : "Answer added — Ask Amina uses it straight away");
      invalidate();
      onDone();
    } catch (e) {
      const fe = fieldErrors(e);
      setErrors(fe);
      if (fe.answer_en) setLang("answer_en");
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <DialogContent
      title={faq ? "Edit answer" : "New answer"}
      size="lg"
      footer={
        <div className="flex items-center justify-between gap-3">
          <label className="flex items-center gap-2.5 text-[14px] font-medium">
            <Switch checked={d.active} onCheckedChange={(v) => setD({ ...d, active: v })} aria-label="Active" /> Active
          </label>
          <Button variant="dark" onClick={save} loading={saving} disabled={!d.question.trim() || !d.answer_en.trim() || !keywords.length}>
            {faq ? "Save answer" : "Add answer"}
          </Button>
        </div>
      }
    >
      <div className="space-y-5 px-6 py-5">
        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_180px]">
          <Field label="Guest question" error={errors.question}>
            <Input value={d.question} onChange={(e) => setD({ ...d, question: e.target.value })} placeholder="Is there parking?" maxLength={160} />
          </Field>
          <Field label="Topic" error={errors.category}>
            <Select value={d.category} onChange={(e) => setD({ ...d, category: e.target.value })}>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {catLabel(c)}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span className="text-[13px] font-semibold">Answer</span>
            <div role="tablist" aria-label="Answer language" className="flex gap-1 rounded-lg bg-surface p-0.5">
              {ANSWER_LANGS.map((l) => (
                <button
                  key={l.key}
                  type="button"
                  role="tab"
                  aria-selected={lang === l.key}
                  onClick={() => setLang(l.key)}
                  className={cn("rounded-md px-2.5 py-1 text-[12.5px] font-semibold", lang === l.key ? "bg-white shadow-sm" : "text-ink-2 hover:text-ink")}
                >
                  {l.label}
                  {d[l.key] && l.key !== "answer_en" && <span className="ml-1 inline-block size-1.5 rounded-full bg-ocean-500 align-middle" />}
                </button>
              ))}
            </div>
          </div>
          <Textarea
            ref={ref}
            value={d[lang]}
            onChange={(e) => setD({ ...d, [lang]: e.target.value })}
            rows={5}
            placeholder={lang === "answer_en" ? "Yes — free secure parking inside the compound at every home." : `Optional — blank uses English: ${d.answer_en.slice(0, 60)}…`}
            aria-label="Answer text"
          />
          {errors[lang] && <p className="mt-1.5 text-[13px] text-danger">{errors[lang]}</p>}
          <div className="mt-2.5 space-y-1.5">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="w-24 text-[12px] font-semibold text-ink-2">Anyone</span>
              {PUBLIC_FACTS.map((p) => (
                <button key={p} type="button" onClick={() => insert(p)} className="rounded-md bg-ocean-50 px-1.5 py-0.5 font-mono text-[11.5px] text-ocean-700 hover:bg-ocean-100">
                  {`{${p}}`}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="w-24 text-[12px] font-semibold text-ink-2">Booked guests</span>
              {BOOKED_FACTS.map((p) => (
                <button key={p} type="button" onClick={() => insert(p)} className="rounded-md bg-brand-50 px-1.5 py-0.5 font-mono text-[11.5px] text-brand-700 hover:bg-brand-100">
                  {`{${p}}`}
                </button>
              ))}
            </div>
          </div>
        </div>

        <Field label="Trigger words" error={errors.keywords} hint="Comma-separated, in English and Kiswahili. Phrases (“check in”) score higher than single words.">
          <Input value={d.keywords} onChange={(e) => setD({ ...d, keywords: e.target.value })} placeholder="parking, park, car, gari, maegesho" />
        </Field>
        {keywords.length > 0 && (
          <div className="-mt-2 flex flex-wrap gap-1.5">
            {keywords.map((k) => (
              <span key={k} className="rounded-full bg-surface px-2.5 py-0.5 text-[12px] font-medium">
                {k}
              </span>
            ))}
          </div>
        )}

        <Field label="Applies to" error={errors.unit}>
          <Select value={d.unit ?? ""} onChange={(e) => setD({ ...d, unit: e.target.value ? Number(e.target.value) : null })}>
            <option value="">All homes</option>
            {(listings ?? []).map((l) => (
              <option key={l.id} value={l.id}>
                Only {l.name}
              </option>
            ))}
          </Select>
        </Field>
      </div>
    </DialogContent>
  );
}
