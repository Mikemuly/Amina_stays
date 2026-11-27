"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleCheck, ClipboardCheck, MessageSquareText, Play, Plus, RotateCcw, Smartphone } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { ErrorBlock, PageHeader, StatusBadge } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogTrigger, SheetContent } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Avatar, Badge, Skeleton } from "@/components/ui/misc";
import { get, patch, post } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { CountPill, MiniEmpty, PriorityChip, RelTime, Segmented, TASK_TYPES, TaskTypeIcon } from "./bits";
import { dueText, useHostAction, useListings, useNow, useStaff } from "./lib";
import type { StaffMember, TaskItem, TaskPriority } from "./types";

const PRIORITIES: { value: TaskPriority; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "normal", label: "Normal" },
  { value: "high", label: "High" },
  { value: "urgent", label: "Urgent" },
];
const RANK: Record<string, number> = { urgent: 0, high: 1, normal: 2, low: 3 };
const SOURCE: Record<string, { label: string; tone: "brand" | "neutral" | "ocean" }> = {
  guest: { label: "Guest reported", tone: "brand" },
  auto: { label: "Auto", tone: "neutral" },
  staff: { label: "Staff", tone: "ocean" },
};
const WEEK = 7 * 86_400_000;
const CATEGORY_LABEL: Record<string, string> = { ac: "AC", wifi: "Wi-Fi" };

const byUrgency = (a: TaskItem, b: TaskItem) =>
  RANK[a.priority] - RANK[b.priority] || (a.due_at ?? "9999").localeCompare(b.due_at ?? "9999") || b.id - a.id;

/** datetime-local value in the browser's zone, e.g. "2026-11-25T14:00". */
function toLocalInput(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function TasksView() {
  const tasks = useQuery({ queryKey: ["host", "ops", "tasks"], queryFn: () => get<TaskItem[]>("/api/host/tasks"), refetchInterval: 10_000 });
  const staff = useStaff();
  const listings = useListings();
  const now = useNow(60_000);
  const [assignee, setAssignee] = React.useState("");
  const [unit, setUnit] = React.useState("");
  const [openId, setOpenId] = React.useState<number | null>(null);

  const people = (staff.data ?? []).filter((s) => s.is_active);
  const filtered = (tasks.data ?? []).filter(
    (t) => (!assignee || (assignee === "none" ? !t.assignee : String(t.assignee) === assignee)) && (!unit || String(t.unit) === unit),
  );
  const columns = [
    { key: "open", title: "Open", tasks: filtered.filter((t) => t.status === "open").sort(byUrgency) },
    { key: "in_progress", title: "In progress", tasks: filtered.filter((t) => t.status === "in_progress").sort(byUrgency) },
    {
      key: "done",
      title: "Done this week",
      tasks: filtered
        .filter((t) => t.status === "done" && (!t.completed_at || !now || now - new Date(t.completed_at).getTime() < WEEK))
        .sort((a, b) => (b.completed_at ?? "").localeCompare(a.completed_at ?? "")),
    },
  ];
  const current = tasks.data?.find((t) => t.id === openId) ?? null;

  return (
    <div>
      <PageHeader
        title="Housekeeping & tasks"
        subtitle="Turnover cleans, repairs and guest requests — assigned to your team by SMS."
        actions={<NewTaskButton staff={people} />}
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <Select aria-label="Filter by assignee" className="h-10 w-auto min-w-44 text-sm" value={assignee} onChange={(e) => setAssignee(e.target.value)}>
              <option value="">Everyone</option>
              <option value="none">Unassigned</option>
              {people.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name || s.phone} · {s.role}
                </option>
              ))}
            </Select>
            <Select aria-label="Filter by home" className="h-10 w-auto min-w-44 text-sm" value={unit} onChange={(e) => setUnit(e.target.value)}>
              <option value="">All homes</option>
              {(listings.data ?? []).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </Select>
            {(assignee || unit) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setAssignee("");
                  setUnit("");
                }}
              >
                Clear
              </Button>
            )}
          </div>

          {tasks.error && !tasks.data ? (
            <ErrorBlock error={tasks.error} retry={() => tasks.refetch()} />
          ) : !tasks.data ? (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-96 rounded-2xl" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-3">
              {columns.map((c) => (
                <section key={c.key} className="rounded-2xl bg-line-soft/50 p-2" aria-label={c.title}>
                  <div className="flex items-center gap-2 px-2 pt-1 pb-2.5">
                    <span
                      className={cn(
                        "size-2 rounded-full",
                        c.key === "open" ? "bg-warning" : c.key === "in_progress" ? "bg-ocean-500" : "bg-success",
                      )}
                    />
                    <h2 className="text-sm font-bold">{c.title}</h2>
                    <CountPill n={c.tasks.length} />
                  </div>
                  {c.tasks.length === 0 ? (
                    <p className="rounded-xl border border-dashed border-line bg-white/60 px-3 py-8 text-center text-[13px] text-ink-2">
                      {c.key === "open" ? "Nothing waiting. Nice." : c.key === "in_progress" ? "No one is on a job right now." : "Nothing finished this week yet."}
                    </p>
                  ) : (
                    <ul className="space-y-2">
                      {c.tasks.map((t) => (
                        <li key={t.id}>
                          <TaskCard task={t} now={now} onOpen={() => setOpenId(t.id)} />
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              ))}
            </div>
          )}
        </div>

        <aside className="space-y-4">
          <SmsHint />
          <TeamCard staff={people} loading={staff.isLoading} />
        </aside>
      </div>

      <Dialog open={current !== null} onOpenChange={(o) => !o && setOpenId(null)}>
        {current && <TaskSheet key={current.id} task={current} staff={people} />}
      </Dialog>
    </div>
  );
}

function TaskCard({ task: t, now, onOpen }: { task: TaskItem; now: number; onOpen: () => void }) {
  const due = dueText(t.due_at, now);
  const doneItems = t.checklist.filter((c) => c.done).length;
  const source = SOURCE[t.source];
  const finished = t.status === "done";
  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-full rounded-xl border border-line-soft bg-white p-3.5 text-left transition hover:border-line hover:shadow-soft focus-visible:ring-2 focus-visible:ring-ink focus-visible:outline-none"
    >
      <div className="flex items-start gap-3">
        <TaskTypeIcon type={t.type} size={32} />
        <div className="min-w-0 flex-1">
          <p className={cn("line-clamp-2 text-sm leading-snug font-semibold", finished && "text-ink-2")}>{t.title}</p>
          <p className="mt-0.5 truncate text-xs text-ink-2">
            {t.unit_name ?? "Any home"} · #{t.id}
          </p>
        </div>
        {!finished && <PriorityChip priority={t.priority} />}
      </div>

      {t.checklist.length > 0 && !finished && (
        <div className="mt-3 flex items-center gap-2">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface">
            <div className="h-full rounded-full bg-ocean-500 transition-[width]" style={{ width: `${(100 * doneItems) / t.checklist.length}%` }} />
          </div>
          <span className="text-[11px] font-semibold text-ink-2 tabular-nums">
            {doneItems}/{t.checklist.length}
          </span>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1.5 text-xs">
        {t.assignee_name ? (
          <span className="inline-flex items-center gap-1.5 font-medium text-ink">
            <Avatar name={t.assignee_name} size={20} /> {t.assignee_name.split(" ")[0]}
          </span>
        ) : (
          <span className="text-ink-3">Unassigned</span>
        )}
        {finished ? (
          <span className="text-success">
            ✓ Done <RelTime at={t.completed_at} />
          </span>
        ) : (
          due.text && <span className={cn(due.overdue ? "font-semibold text-danger" : "text-ink-2")}>{due.text}</span>
        )}
        {source && (
          <Badge tone={source.tone} className="ml-auto px-2 py-0 text-[11px]">
            {source.label}
          </Badge>
        )}
      </div>
      {finished && t.completion_note && <p className="mt-2 line-clamp-2 rounded-lg bg-surface px-2.5 py-1.5 text-xs text-ink-2">“{t.completion_note}”</p>}
    </button>
  );
}

// ---------- detail sheet ----------

function TaskSheet({ task: t, staff }: { task: TaskItem; staff: StaffMember[] }) {
  const [finishing, setFinishing] = React.useState(false);
  const [note, setNote] = React.useState("");
  const update = useHostAction((body: Partial<Pick<TaskItem, "priority" | "assignee" | "due_at" | "status" | "checklist">>) =>
    patch<TaskItem>(`/api/host/tasks/${t.id}`, body),
  );
  const start = useHostAction(() => post(`/api/host/tasks/${t.id}/start`), { success: `Task #${t.id} started` });
  const complete = useHostAction(() => post(`/api/host/tasks/${t.id}/complete`, { note: note.trim() }), {
    success: `Task #${t.id} done`,
    onSuccess: () => setFinishing(false),
  });
  const checklist = update.isPending && update.variables?.checklist ? update.variables.checklist : t.checklist;
  const priority = update.isPending && update.variables?.priority ? update.variables.priority : t.priority;
  const meta = TASK_TYPES[t.type] ?? TASK_TYPES.other;
  const source = SOURCE[t.source];
  const closed = t.status === "done" || t.status === "cancelled";

  const footer = closed ? (
    <div className="flex justify-between gap-2">
      <span className="self-center text-[13px] text-ink-2">{t.status === "done" ? <>Finished {fmtDateTime(t.completed_at)}</> : "Cancelled"}</span>
      <Button variant="soft" loading={update.isPending && update.variables?.status === "open"} onClick={() => update.mutate({ status: "open" })}>
        <RotateCcw className="size-4" /> Reopen
      </Button>
    </div>
  ) : finishing ? (
    <div className="space-y-3">
      <Field label="Completion note (optional)">
        <Textarea autoFocus className="min-h-20" maxLength={300} placeholder="e.g. Replaced the AC remote batteries" value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" onClick={() => setFinishing(false)}>
          Back
        </Button>
        <Button variant="dark" loading={complete.isPending} onClick={() => complete.mutate()}>
          <CircleCheck className="size-4" /> Mark done
        </Button>
      </div>
    </div>
  ) : (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <Button variant="ghost" className="text-danger hover:bg-danger-50" loading={update.isPending && update.variables?.status === "cancelled"} onClick={() => update.mutate({ status: "cancelled" })}>
        Cancel task
      </Button>
      <div className="flex gap-2">
        {t.status === "open" && (
          <Button variant="soft" loading={start.isPending} onClick={() => start.mutate()}>
            <Play className="size-4" /> Start
          </Button>
        )}
        <Button variant="dark" onClick={() => setFinishing(true)}>
          <CircleCheck className="size-4" /> Mark done
        </Button>
      </div>
    </div>
  );

  return (
    <SheetContent title={`#${t.id} · ${meta.label}`} width="max-w-lg" footer={footer}>
      <div className="space-y-6 p-6">
        <div className="flex items-start gap-3">
          <TaskTypeIcon type={t.type} size={44} />
          <div className="min-w-0">
            <h3 className="text-lg leading-snug font-bold">{t.title}</h3>
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <StatusBadge status={t.status} />
              {source && <Badge tone={source.tone}>{source.label}</Badge>}
              {t.category && <Badge>{CATEGORY_LABEL[t.category] ?? t.category.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())}</Badge>}
            </div>
          </div>
        </div>

        {t.description && <p className="rounded-xl bg-surface px-4 py-3 text-sm whitespace-pre-wrap">{t.description}</p>}

        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <div>
            <dt className="text-[13px] text-ink-2">Home</dt>
            <dd className="mt-0.5 font-medium">{t.unit_name ?? "Any home"}</dd>
          </div>
          <div>
            <dt className="text-[13px] text-ink-2">Booking</dt>
            <dd className="mt-0.5 font-medium">
              {t.booking_ref ? (
                <Link href={`/host/reservations/${t.booking_ref}`} className="hover:underline">
                  {t.booking_ref}
                </Link>
              ) : (
                "—"
              )}
            </dd>
          </div>
          <div>
            <dt className="text-[13px] text-ink-2">Created</dt>
            <dd className="mt-0.5 font-medium">
              <RelTime at={t.created_at} />
            </dd>
          </div>
          <div>
            <dt className="text-[13px] text-ink-2">Started</dt>
            <dd className="mt-0.5 font-medium">{t.started_at ? fmtDateTime(t.started_at) : "—"}</dd>
          </div>
        </dl>

        <div className="space-y-4 border-t border-line-soft pt-5">
          <Field label="Priority">
            <Segmented label="Priority" value={priority} onChange={(v) => !closed && update.mutate({ priority: v })} options={PRIORITIES} size="sm" />
          </Field>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="Assigned to" hint="They get the task by SMS.">
              <Select
                value={t.assignee ? String(t.assignee) : ""}
                disabled={closed || update.isPending}
                onChange={(e) => update.mutate({ assignee: e.target.value ? Number(e.target.value) : null })}
              >
                <option value="">Unassigned</option>
                {staff.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name || s.phone} · {s.role}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Due">
              <Input
                type="datetime-local"
                disabled={closed}
                defaultValue={toLocalInput(t.due_at)}
                onBlur={(e) => {
                  const v = e.target.value;
                  if (v !== toLocalInput(t.due_at)) update.mutate({ due_at: v ? new Date(v).toISOString() : null });
                }}
              />
            </Field>
          </div>
        </div>

        {checklist.length > 0 && (
          <div className="border-t border-line-soft pt-5">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-[13px] font-semibold">Checklist</p>
              <span className="text-xs text-ink-2 tabular-nums">
                {checklist.filter((c) => c.done).length} of {checklist.length}
              </span>
            </div>
            <ul className="space-y-1">
              {checklist.map((c, i) => (
                <li key={i}>
                  <label className={cn("flex cursor-pointer items-start gap-3 rounded-lg px-2 py-2 hover:bg-surface", closed && "cursor-default")}>
                    <input
                      type="checkbox"
                      className="mt-0.5 size-4 accent-[#0e8388]"
                      checked={c.done}
                      disabled={closed}
                      onChange={() => update.mutate({ checklist: checklist.map((x, j) => (j === i ? { ...x, done: !x.done } : x)) })}
                    />
                    <span className={cn("text-sm", c.done && "text-ink-3 line-through")}>{c.item}</span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        )}

        {t.completion_note && (
          <div className="border-t border-line-soft pt-5">
            <p className="text-[13px] font-semibold">Completion note</p>
            <p className="mt-1 text-sm text-ink-2">“{t.completion_note}”</p>
          </div>
        )}
      </div>
    </SheetContent>
  );
}

// ---------- new task ----------

function NewTaskButton({ staff }: { staff: StaffMember[] }) {
  const [open, setOpen] = React.useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="dark">
          <Plus className="size-4" strokeWidth={2.5} /> New task
        </Button>
      </DialogTrigger>
      {open && <NewTaskForm staff={staff} onDone={() => setOpen(false)} />}
    </Dialog>
  );
}

function NewTaskForm({ staff, onDone }: { staff: StaffMember[]; onDone: () => void }) {
  const { data: listings } = useListings();
  const [type, setType] = React.useState("turnover");
  const [title, setTitle] = React.useState("");
  const [unit, setUnit] = React.useState("");
  const [priority, setPriority] = React.useState<TaskPriority>("normal");
  const [assignee, setAssignee] = React.useState("");
  const [due, setDue] = React.useState("");
  const [description, setDescription] = React.useState("");
  const unitName = listings?.find((l) => String(l.id) === unit)?.name;
  const placeholder = `${TASK_TYPES[type]?.label ?? "Task"}${unitName ? ` - ${unitName}` : ""}`;
  const person = staff.find((s) => String(s.id) === assignee);

  const create = useHostAction(
    () =>
      post<TaskItem>("/api/host/tasks", {
        type,
        title: (title.trim() || placeholder).slice(0, 140),
        unit: unit ? Number(unit) : null,
        priority,
        assignee: assignee ? Number(assignee) : null,
        due_at: due ? new Date(due).toISOString() : null,
        description: description.trim(),
      }),
    {
      success: (t) => `Task #${t.id} created${person ? ` — ${person.name?.split(" ")[0] || "assignee"} notified by SMS` : ""}`,
      onSuccess: onDone,
    },
  );

  return (
    <DialogContent
      size="md"
      title="New task"
      footer={
        <div className="flex justify-end gap-2">
          <DialogClose asChild>
            <Button variant="ghost">Cancel</Button>
          </DialogClose>
          <Button type="submit" form="new-task" variant="dark" loading={create.isPending}>
            Create task
          </Button>
        </div>
      }
    >
      <form
        id="new-task"
        className="grid grid-cols-1 gap-4 px-6 py-5 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <Field label="Type">
          <Select value={type} onChange={(e) => setType(e.target.value)}>
            {Object.entries(TASK_TYPES).map(([k, v]) => (
              <option key={k} value={k}>
                {v.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Home">
          <Select value={unit} onChange={(e) => setUnit(e.target.value)}>
            <option value="">Any / not home-specific</option>
            {(listings ?? []).map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Title" className="sm:col-span-2">
          <Input maxLength={140} placeholder={placeholder} value={title} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label="Priority" className="sm:col-span-2">
          <Segmented label="Priority" value={priority} onChange={setPriority} options={PRIORITIES} size="sm" />
        </Field>
        <Field label="Assign to" hint={person ? `${person.name || person.phone} gets an SMS with the task.` : "Leave unassigned to decide later."}>
          <Select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
            <option value="">Unassigned</option>
            {staff.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name || s.phone} · {s.role}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Due">
          <Input type="datetime-local" value={due} onChange={(e) => setDue(e.target.value)} />
        </Field>
        <Field label="Details" className="sm:col-span-2" hint={type === "turnover" ? "Turnover cleans get the standard 7-step checklist." : undefined}>
          <Textarea className="min-h-20" placeholder="What needs doing, where, anything to bring…" value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
      </form>
    </DialogContent>
  );
}

// ---------- side panel ----------

function SmsHint() {
  return (
    <section className="overflow-hidden rounded-2xl border border-line-soft bg-white">
      <div className="border-b border-line-soft px-5 py-3.5">
        <h2 className="flex items-center gap-2 text-[15px] font-bold">
          <Smartphone className="size-4 text-ink-2" /> Runs on any phone
        </h2>
        <p className="mt-0.5 text-[13px] text-ink-2">Staff don&apos;t need an app — every task is a text message.</p>
      </div>
      <div className="space-y-2 bg-surface/60 px-4 py-4 text-[13px]">
        <div className="max-w-[88%] rounded-2xl rounded-bl-md bg-white px-3 py-2 shadow-sm ring-1 ring-line-soft">
          New task #12: Turnover clean - Blue Reef Apartment, due today 1:00pm. Reply DONE 12 when finished, or START 12.
        </div>
        <div className="ml-auto w-fit rounded-2xl rounded-br-md bg-ink px-3 py-2 font-semibold text-white">DONE 12</div>
        <div className="max-w-[88%] rounded-2xl rounded-bl-md bg-white px-3 py-2 shadow-sm ring-1 ring-line-soft">Asante! Task #12 is closed ✓</div>
      </div>
      <ul className="space-y-1.5 px-5 py-4 text-[13px] text-ink-2">
        <li>
          <span className="font-mono font-semibold text-ink">START 12</span> — marks the job in progress
        </li>
        <li>
          <span className="font-mono font-semibold text-ink">DONE 12</span> — closes it; the home is marked clean
        </li>
        <li>
          <span className="font-mono font-semibold text-ink">TASKS</span> — lists their open jobs
        </li>
      </ul>
    </section>
  );
}

function TeamCard({ staff, loading }: { staff: StaffMember[]; loading: boolean }) {
  const team = staff.filter((s) => !["owner", "manager"].includes(s.role));
  return (
    <section className="rounded-2xl border border-line-soft bg-white">
      <div className="flex items-center justify-between border-b border-line-soft px-5 py-3.5">
        <h2 className="flex items-center gap-2 text-[15px] font-bold">
          <ClipboardCheck className="size-4 text-ink-2" /> Team
        </h2>
        <Link href="/host/settings" className="text-[13px] font-semibold text-ink-2 hover:text-ink">
          Manage →
        </Link>
      </div>
      {loading ? (
        <div className="space-y-3 p-5">
          <Skeleton className="h-9" />
          <Skeleton className="h-9" />
        </div>
      ) : team.length === 0 ? (
        <MiniEmpty icon={<MessageSquareText />} title="No staff yet">
          Add your cleaner and caretaker so tasks reach them by SMS.
        </MiniEmpty>
      ) : (
        <ul className="divide-y divide-line-soft">
          {team.map((s) => (
            <li key={s.id} className="flex items-center gap-3 px-5 py-3">
              <Avatar name={s.name || s.phone} size={32} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{s.name || s.phone}</p>
                <p className="text-xs text-ink-2 capitalize">{s.role}</p>
              </div>
              <span className={cn("text-xs font-semibold tabular-nums", s.open_tasks ? "text-ink" : "text-ink-3")}>
                {s.open_tasks ? `${s.open_tasks} open` : "Free"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
