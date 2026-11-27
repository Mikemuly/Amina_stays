"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw, Search } from "lucide-react";
import { useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { ErrorBlock, LoadingBlock } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Badge, EmptyState } from "@/components/ui/misc";
import { del, get, put } from "@/lib/api";
import { plural } from "@/lib/format";
import { cn } from "@/lib/utils";

import { SAMPLE_VALUES, renderPlaceholders, smsInfo } from "./sms";
import type { TemplateItem, TemplateLang, TemplatesResponse } from "./types";
import { ConfirmDialog, PhonePreview, SmsMeter, errorMessage, humanize, replaceSearchParams } from "./ui";

const LANGS: { value: TemplateLang; label: string }[] = [
  { value: "en", label: "English" },
  { value: "sw", label: "Kiswahili" },
  { value: "it", label: "Italiano" },
  { value: "de", label: "Deutsch" },
  { value: "fr", label: "Français" },
];

const GROUPS: [string, string[]][] = [
  ["Guest timeline", ["booking_confirmed", "balance_note", "pre_arrival", "id_request", "balance_due", "directions", "checkin_code", "local_tips", "arrival_tips", "welcome_check", "mid_stay", "checkout_reminder", "checkout_thanks", "review_request", "rebook_offer"]],
  ["Booking & payments", ["hold_mpesa", "hold_card", "payment_failed", "payment_received", "hold_expired", "late_payment_refund", "refund_line", "cancel_quote", "cancelled_by_guest", "cancelled_by_host", "goodwill_line", "request_sent", "request_approved", "request_declined", "waitlist_offer", "kept", "taken"]],
  ["Arrival & door code", ["code_waiting_balance", "code_waiting_id", "code_security_hold", "arrival_question", "eta_saved", "id_saved", "auto_checkout"]],
  ["Ask Amina — SMS bot", ["menu", "options", "ask_dates", "none_free", "price_list", "status", "no_booking", "help_ack", "help_alerted", "help_calling", "relay_ack", "issue_logged", "issue_fixed", "breakfast_menu", "breakfast_saved", "breakfast_none", "lang_set", "opted_in", "opted_out", "goodbye_ack", "review_comment", "review_thanks", "review_sorry"]],
  ["Team & host", ["staff_task", "kitchen_sheet", "gate_list", "host_digest"]],
  ["Account", ["otp"]],
];

const NAMES: Record<string, string> = {
  otp: "Login code", hold_mpesa: "Holding — M-Pesa prompt", hold_card: "Holding — card payment link", checkin_code: "Door code", local_tips: "Local tips",
  welcome_check: "Settled in?", mid_stay: "Mid-stay check-in", rebook_offer: "Come-back offer", gate_list: "Gate list (security)",
  host_digest: "Morning digest (to you)", kitchen_sheet: "Kitchen sheet (cook)", staff_task: "New task (staff)", menu: "Main menu",
  id_request: "Guest-register ID reminder", code_security_hold: "Door code held — SIM swap", code_waiting_id: "Door code waiting for ID",
  code_waiting_balance: "Door code waiting for balance", relay_ack: "Question passed to Amina", help_alerted: "SOS — help alerted",
  help_calling: "SOS — calling now", help_ack: "SOS received", kept: "Booking kept", taken: "Dates just taken", eta_saved: "Arrival time saved",
};

const templateName = (key: string) => NAMES[key] ?? humanize(key);
const PLACEHOLDER_RE = /\{(\w+)\}/g;
const placeholdersIn = (text: string) => [...text.matchAll(PLACEHOLDER_RE)].map((m) => m[1]);

export function TemplatesTab() {
  const sp = useSearchParams();
  const qc = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["host", "templates"], queryFn: () => get<TemplatesResponse>("/api/host/templates") });
  const [q, setQ] = React.useState("");
  const [drafts, setDrafts] = React.useState<Record<string, string>>({});

  if (error) return <ErrorBlock error={error} retry={refetch} />;
  if (isLoading || !data) return <LoadingBlock rows={6} />;

  const byKey = new Map(data.templates.map((t) => [t.key, t]));
  const selectedKey = sp.get("key") && byKey.has(sp.get("key") as string) ? (sp.get("key") as string) : "pre_arrival";
  const selected = byKey.get(selectedKey) ?? data.templates[0];
  const needle = q.trim().toLowerCase();
  const grouped = new Set(GROUPS.flatMap(([, keys]) => keys));
  const groups: [string, TemplateItem[]][] = [
    ...GROUPS.map(([label, keys]) => [label, keys.map((k) => byKey.get(k)).filter((t): t is TemplateItem => !!t)] as [string, TemplateItem[]]),
    ["Other", data.templates.filter((t) => !grouped.has(t.key))] as [string, TemplateItem[]],
  ]
    .map(([label, items]): [string, TemplateItem[]] => [
      label,
      items.filter((t) => !needle || t.key.includes(needle) || templateName(t.key).toLowerCase().includes(needle) || t.description.toLowerCase().includes(needle) || t.langs.en.body.toLowerCase().includes(needle)),
    ])
    .filter(([, items]) => items.length > 0);
  const customCount = data.templates.filter((t) => Object.values(t.langs).some((l) => l.custom)).length;
  const unsaved = (key: string) => Object.keys(drafts).some((k) => k.startsWith(`${key}:`));

  return (
    <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
      <aside className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-line-soft bg-white lg:sticky lg:top-6 lg:max-h-[calc(100dvh-3rem)] lg:self-start">
        <div className="border-b border-line-soft p-3">
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Search ${data.templates.length} messages`} aria-label="Search templates" className="h-9 pl-9 text-sm" />
          </div>
          <p className="mt-2 px-1 text-[12px] text-ink-2">{customCount ? `${plural(customCount, "message")} customised` : "All messages use the built-in wording"}</p>
        </div>
        <nav aria-label="Message templates" className="max-h-80 min-h-0 flex-1 overflow-y-auto py-2 lg:max-h-none">
          {groups.length === 0 && <p className="px-4 py-6 text-center text-sm text-ink-2">No messages match “{q}”.</p>}
          {groups.map(([label, items]) => (
            <div key={label} className="mb-2">
              <p className="px-4 pt-2 pb-1 text-[11px] font-bold tracking-wider text-ink-3 uppercase">{label}</p>
              {items.map((t) => {
                const active = t.key === selected.key;
                const custom = Object.values(t.langs).some((l) => l.custom);
                return (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => replaceSearchParams({ key: t.key })}
                    aria-current={active ? "true" : undefined}
                    className={cn("flex w-full items-start gap-2 px-4 py-2 text-left transition-colors", active ? "bg-surface" : "hover:bg-surface/60")}
                  >
                    <span className="min-w-0 flex-1">
                      <span className={cn("block truncate text-[13.5px]", active ? "font-bold" : "font-medium")}>{templateName(t.key)}</span>
                      {t.description && <span className="block truncate text-[12px] text-ink-2">{t.description}</span>}
                    </span>
                    {unsaved(t.key) ? (
                      <span className="mt-1.5 size-2 shrink-0 rounded-full bg-brand-500" title="Unsaved changes" />
                    ) : custom ? (
                      <span className="mt-0.5 shrink-0 rounded-full bg-ocean-50 px-1.5 text-[10.5px] font-bold text-ocean-700">Custom</span>
                    ) : null}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>

      {selected ? (
        <TemplateEditor
          key={selected.key}
          template={selected}
          placeholders={data.placeholders}
          drafts={drafts}
          setDraft={(lang, body) =>
            setDrafts((d) => {
              const k = `${selected.key}:${lang}`;
              const next = { ...d };
              if (body === null || body === selected.langs[lang].body) delete next[k];
              else next[k] = body;
              return next;
            })
          }
          onChanged={() => qc.invalidateQueries({ queryKey: ["host", "templates"] })}
        />
      ) : (
        <EmptyState title="Choose a message" />
      )}
    </div>
  );
}

function TemplateEditor({
  template: t, placeholders, drafts, setDraft, onChanged,
}: {
  template: TemplateItem;
  placeholders: string[];
  drafts: Record<string, string>;
  setDraft: (lang: TemplateLang, body: string | null) => void;
  onChanged: () => void;
}) {
  const [lang, setLang] = React.useState<TemplateLang>("en");
  const [saving, setSaving] = React.useState(false);
  const [confirmReset, setConfirmReset] = React.useState(false);
  const [resetting, setResetting] = React.useState(false);
  const ref = React.useRef<HTMLTextAreaElement>(null);

  const server = t.langs[lang];
  const body = drafts[`${t.key}:${lang}`] ?? server.body;
  const dirty = body !== server.body;
  const fallback = !server.body && !server.default;
  const known = new Set([...placeholders, ...Object.values(t.langs).flatMap((l) => placeholdersIn(l.default)), "s"]);
  const unknown = [...new Set(placeholdersIn(body).filter((p) => !known.has(p)))];
  const rendered = renderPlaceholders(body || t.langs.en.body, SAMPLE_VALUES);
  const renderedInfo = smsInfo(rendered);

  const setBody = (v: string) => setDraft(lang, v);

  const insert = (ph: string) => {
    const token = `{${ph}}`;
    const el = ref.current;
    if (!el) return setBody(body + token);
    const start = el.selectionStart ?? body.length;
    const end = el.selectionEnd ?? body.length;
    setBody(body.slice(0, start) + token + body.slice(end));
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + token.length, start + token.length);
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      const r = await put<{ segments: number }>(`/api/host/templates/${t.key}/${lang}`, { body: body.trim() });
      toast.success(`${templateName(t.key)} saved`, { description: `${LANGS.find((l) => l.value === lang)?.label} · ${plural(r.segments, "SMS part")} before placeholders are filled in` });
      setDraft(lang, null);
      onChanged();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    setResetting(true);
    try {
      await del(`/api/host/templates/${t.key}/${lang}`);
      toast.success("Back to the built-in wording");
      setDraft(lang, null);
      setConfirmReset(false);
      onChanged();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setResetting(false);
    }
  };

  return (
    <section className="min-w-0 rounded-2xl border border-line-soft bg-white">
      <header className="border-b border-line-soft px-5 py-4 sm:px-6">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-[19px] font-bold tracking-tight">{templateName(t.key)}</h2>
          {server.custom && <Badge tone="ocean">Custom</Badge>}
          <code className="rounded bg-surface px-1.5 py-0.5 font-mono text-[11.5px] text-ink-2">{t.key}</code>
        </div>
        {t.description && <p className="mt-1 text-[14px] text-ink-2">{t.description}</p>}
      </header>

      <div className="grid gap-6 px-5 py-5 sm:px-6 xl:grid-cols-[minmax(0,1fr)_330px]">
        <div className="min-w-0 space-y-4">
          <div role="tablist" aria-label="Language" className="no-scrollbar flex gap-1 overflow-x-auto rounded-xl bg-surface p-1">
            {LANGS.map((l) => {
              const info = t.langs[l.value];
              const has = drafts[`${t.key}:${l.value}`] !== undefined;
              return (
                <button
                  key={l.value}
                  type="button"
                  role="tab"
                  aria-selected={lang === l.value}
                  onClick={() => setLang(l.value)}
                  className={cn(
                    "flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-semibold transition",
                    lang === l.value ? "bg-white text-ink shadow-sm" : "text-ink-2 hover:text-ink",
                    !info.body && !has && "text-ink-3",
                  )}
                >
                  {l.label}
                  {has ? (
                    <span className="size-1.5 rounded-full bg-brand-500" />
                  ) : info.custom ? (
                    <span className="size-1.5 rounded-full bg-ocean-500" />
                  ) : !info.body ? (
                    <span className="text-[11px] font-normal">—</span>
                  ) : null}
                </button>
              );
            })}
          </div>

          {fallback && !dirty && (
            <p className="rounded-lg bg-warning-50 px-3 py-2 text-[13px] text-warning">
              No {LANGS.find((l) => l.value === lang)?.label} version yet — these guests get the English text. Write one below to send it in their language.
            </p>
          )}

          <Textarea
            ref={ref}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={7}
            placeholder={t.langs.en.body}
            aria-label={`${templateName(t.key)} (${lang})`}
            className="text-[15px]"
          />
          <SmsMeter text={body} onFix={setBody} />
          {unknown.length > 0 && (
            <p className="text-[12.5px] text-warning">
              {unknown.map((u) => `{${u}}`).join(", ")} isn&apos;t filled in for this message and will be left blank.
            </p>
          )}

          <div>
            <p className="mb-2 text-[12px] font-semibold tracking-wide text-ink-2 uppercase">Insert a placeholder</p>
            <div className="flex flex-wrap gap-1.5">
              {placeholders.map((p) => {
                const used = body.includes(`{${p}}`);
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() => insert(p)}
                    className={cn(
                      "rounded-md border px-2 py-1 font-mono text-[12px] transition",
                      used ? "border-ink bg-ink text-white" : "border-line-soft bg-surface text-ink-2 hover:border-ink-3 hover:text-ink",
                    )}
                  >
                    {`{${p}}`}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 border-t border-line-soft pt-4">
            {server.custom && (
              <Button variant="ghost" size="sm" onClick={() => setConfirmReset(true)}>
                <RotateCcw className="size-4" /> Reset to default
              </Button>
            )}
            <div className="ml-auto flex gap-2">
              {dirty && (
                <Button variant="ghost" onClick={() => setDraft(lang, null)} disabled={saving}>
                  Discard
                </Button>
              )}
              <Button variant="dark" onClick={save} loading={saving} disabled={!dirty || !body.trim()}>
                Save {LANGS.find((l) => l.value === lang)?.label}
              </Button>
            </div>
          </div>
        </div>

        <div>
          <PhonePreview text={rendered || "—"} footer={`With sample data: ${plural(renderedInfo.segments, "SMS part")} · ${renderedInfo.length} characters`} />
        </div>
      </div>

      <ConfirmDialog
        open={confirmReset}
        onOpenChange={setConfirmReset}
        title="Reset to the built-in wording?"
        confirmLabel="Reset"
        loading={resetting}
        onConfirm={reset}
      >
        Your custom {LANGS.find((l) => l.value === lang)?.label} text for “{templateName(t.key)}” will be replaced by the default:
        <span className="mt-3 block rounded-lg bg-surface p-3 text-[14px] text-ink">{server.default || "(no default — English is used)"}</span>
      </ConfirmDialog>
    </section>
  );
}
