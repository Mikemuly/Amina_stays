"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { MessageSquareText, Pencil, Plus, UserMinus, Users } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { useMe } from "@/components/providers";
import { ErrorBlock, LoadingBlock, Table, Td, Tr } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { Avatar, Badge } from "@/components/ui/misc";
import { Switch, Tooltip } from "@/components/ui/overlays";
import { del, get, patch, post } from "@/lib/api";
import { plural } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useInvalidateHost, useListings } from "./queries";
import type { RoleOption, StaffMember } from "./types";
import { Callout, ConfirmDialog, Field, IconButton, TableCard, errorMessage, fieldErrors } from "./ui";

const LANGS: Record<string, string> = { en: "English", sw: "Kiswahili", fr: "Français", de: "Deutsch", it: "Italiano" };
const CONSOLE_ROLES = ["owner", "manager"];
const ROLE_TONE: Record<string, "dark" | "ocean" | "brand" | "neutral" | "warning"> = {
  owner: "dark", manager: "ocean", cleaner: "neutral", cook: "brand", caretaker: "warning", security: "neutral", driver: "neutral",
};

const COMMANDS: [string, string][] = [
  ["TASKS", "their open jobs"],
  ["START 12", "starts task #12"],
  ["DONE 12", "closes it (IMEISHA 12 works too)"],
  ["BREAKFAST", "tomorrow's kitchen sheet (cook)"],
  ["GATE", "today's arrivals and car plates (security)"],
];

export function TeamTab() {
  const invalidate = useInvalidateHost();
  const { data: me } = useMe();
  const staffQ = useQuery({ queryKey: ["host", "staff"], queryFn: () => get<StaffMember[]>("/api/host/staff") });
  const rolesQ = useQuery({ queryKey: ["host", "roles"], queryFn: () => get<RoleOption[]>("/api/host/roles"), staleTime: 10 * 60_000 });
  const { data: listings } = useListings();
  const [editing, setEditing] = React.useState<StaffMember | "new" | null>(null);
  const [removing, setRemoving] = React.useState<StaffMember | null>(null);

  const toggle = useMutation({
    mutationFn: (s: StaffMember) => patch<StaffMember>(`/api/host/staff/${s.id}`, { is_active: !s.is_active }),
    onSuccess: (s) => {
      toast.success(s.is_active ? `${s.name || s.phone} is active again` : `${s.name || s.phone} paused — no new tasks or sheets`);
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const remove = useMutation({
    mutationFn: (s: StaffMember) => del(`/api/host/staff/${s.id}`),
    onSuccess: () => {
      toast.success("Removed from the team");
      setRemoving(null);
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const roles = rolesQ.data ?? [];
  const roleLabel = (r: string) => roles.find((x) => x.value === r)?.label ?? r;
  const unitCount = listings?.length ?? 0;
  const homes = (ids: number[]) =>
    ids.length === 0 ? "—" : unitCount && ids.length >= unitCount ? "All homes" : ids.map((id) => listings?.find((l) => l.id === id)?.name ?? `#${id}`).join(", ");

  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Callout tone="info" icon={<MessageSquareText className="size-[18px]" />} title="Your team works entirely by SMS — no app, no smartphone">
          Cleaners, the cook, the caretaker and security get tasks and daily sheets by text and reply in English or Kiswahili. Anything else they text is
          forwarded to you.
        </Callout>
        <div className="rounded-xl border border-line-soft bg-white px-4 py-3.5">
          <p className="text-[13px] font-semibold">What they can reply</p>
          <ul className="mt-2 grid gap-x-4 gap-y-1.5 text-[13px] sm:grid-cols-2">
            {COMMANDS.map(([cmd, what]) => (
              <li key={cmd} className="flex items-baseline gap-2">
                <code className="shrink-0 rounded bg-surface px-1.5 py-0.5 font-mono text-[12px] font-semibold">{cmd}</code>
                <span className="text-ink-2">{what}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <TableCard
        title="Team"
        description={staffQ.data ? `${plural(staffQ.data.length, "person", "people")} · owners and managers can also log in to this console` : undefined}
        action={
          <Button variant="dark" size="sm" onClick={() => setEditing("new")}>
            <Plus className="size-4" /> Add team member
          </Button>
        }
      >
        {staffQ.error ? (
          <div className="p-5">
            <ErrorBlock error={staffQ.error} retry={staffQ.refetch} />
          </div>
        ) : staffQ.isLoading ? (
          <div className="p-5">
            <LoadingBlock rows={4} />
          </div>
        ) : (
          <Table head={["Person", "Role", "Messages in", "Homes", "Open tasks", "Active", ""]} empty="No team members yet.">
            {(staffQ.data ?? []).map((s) => {
              const self = me?.id === s.id;
              return (
                <Tr key={s.id} className={cn(!s.is_active && "opacity-60")}>
                  <Td>
                    <div className="flex items-center gap-3">
                      <Avatar name={s.name || "Team"} size={36} />
                      <div className="min-w-0">
                        <p className="font-semibold">
                          {s.name || "Unnamed"} {self && <span className="text-[12px] font-normal text-ink-2">(you)</span>}
                        </p>
                        <p className="font-mono text-[12px] text-ink-2">{s.phone}</p>
                      </div>
                    </div>
                  </Td>
                  <Td>
                    <Badge tone={ROLE_TONE[s.role] ?? "neutral"}>{roleLabel(s.role)}</Badge>
                    {CONSOLE_ROLES.includes(s.role) && <span className="mt-0.5 block text-[11.5px] text-ink-2">Console access</span>}
                  </Td>
                  <Td className="text-ink-2">{LANGS[s.lang] ?? s.lang}</Td>
                  <Td className="max-w-56 truncate text-ink-2" title={homes(s.unit_ids)}>
                    {homes(s.unit_ids)}
                  </Td>
                  <Td className="tabular-nums">{s.open_tasks || <span className="text-ink-3">0</span>}</Td>
                  <Td>
                    <Switch
                      checked={s.is_active}
                      disabled={self || toggle.isPending}
                      onCheckedChange={() => toggle.mutate(s)}
                      aria-label={`${s.name || s.phone} active`}
                    />
                  </Td>
                  <Td className="text-right whitespace-nowrap">
                    <IconButton label="Edit" onClick={() => setEditing(s)}>
                      <Pencil />
                    </IconButton>
                    {!self && s.role !== "owner" && (
                      <IconButton label="Remove from team" tone="danger" onClick={() => setRemoving(s)}>
                        <UserMinus />
                      </IconButton>
                    )}
                  </Td>
                </Tr>
              );
            })}
          </Table>
        )}
      </TableCard>

      <Dialog open={editing !== null} onOpenChange={(v) => !v && setEditing(null)}>
        {editing !== null && (
          <StaffEditor member={editing === "new" ? null : editing} roles={roles} isSelf={editing !== "new" && me?.id === editing.id} onDone={() => setEditing(null)} />
        )}
      </Dialog>

      <ConfirmDialog
        open={!!removing}
        onOpenChange={(v) => !v && setRemoving(null)}
        title={`Remove ${removing?.name || removing?.phone || "this person"}?`}
        confirmLabel="Remove from team"
        tone="danger"
        loading={remove.isPending}
        onConfirm={() => removing && remove.mutate(removing)}
      >
        They stop getting tasks and sheets, and their SMS commands stop working. Their number stays a normal guest account; open tasks keep their history.
      </ConfirmDialog>
    </div>
  );
}

function StaffEditor({ member, roles, isSelf, onDone }: { member: StaffMember | null; roles: RoleOption[]; isSelf: boolean; onDone: () => void }) {
  const invalidate = useInvalidateHost();
  const { data: listings } = useListings();
  const [d, setD] = React.useState(() => ({
    phone: member?.phone ?? "",
    name: member?.name ?? "",
    role: member?.role ?? "cleaner",
    lang: member?.lang ?? "sw",
    is_active: member?.is_active ?? true,
    unit_ids: member?.unit_ids ?? (listings ?? []).map((l) => l.id),
  }));
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [saving, setSaving] = React.useState(false);
  const all = listings ?? [];
  const allSelected = all.length > 0 && all.every((l) => d.unit_ids.includes(l.id));

  const save = async () => {
    setSaving(true);
    setErrors({});
    try {
      if (member) await patch(`/api/host/staff/${member.id}`, d);
      else await post("/api/host/staff", d);
      toast.success(member ? "Team member updated" : `${d.name || d.phone} added`, { description: member ? undefined : "They can text TASKS to the Amina Stays number right away." });
      invalidate();
      onDone();
    } catch (e) {
      setErrors(fieldErrors(e));
      toast.error(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <DialogContent
      title={member ? "Edit team member" : "Add team member"}
      footer={
        <div className="flex items-center justify-between gap-3">
          <label className="flex items-center gap-2.5 text-[14px] font-medium">
            <Switch checked={d.is_active} disabled={isSelf} onCheckedChange={(v) => setD({ ...d, is_active: v })} aria-label="Active" /> Active
          </label>
          <Button variant="dark" onClick={save} loading={saving} disabled={!d.phone.trim()}>
            {member ? "Save changes" : "Add to team"}
          </Button>
        </div>
      }
    >
      <div className="space-y-4 px-6 py-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Phone number" error={errors.phone} hint={member ? "Their login and SMS identity." : "Kenyan or international, e.g. 0712 345 678."}>
            <Input value={d.phone} onChange={(e) => setD({ ...d, phone: e.target.value })} placeholder="0712 345 678" className="font-mono" disabled={!!member} />
          </Field>
          <Field label="Name" error={errors.name}>
            <Input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} placeholder="Fatuma Ali" />
          </Field>
          <Field label="Role" error={errors.role} hint={CONSOLE_ROLES.includes(d.role) ? "Can log in to this console." : "SMS only — no console access."}>
            <Select value={d.role} onChange={(e) => setD({ ...d, role: e.target.value })} disabled={isSelf}>
              {roles.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Messages in" error={errors.lang}>
            <Select value={d.lang} onChange={(e) => setD({ ...d, lang: e.target.value })}>
              {Object.entries(LANGS).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <div>
          <div className="mb-2 flex items-center justify-between">
            <p className="text-[13px] font-semibold">Homes they look after</p>
            <button
              type="button"
              className="text-[13px] font-semibold text-ink-2 underline underline-offset-2 hover:text-ink"
              onClick={() => setD({ ...d, unit_ids: allSelected ? [] : all.map((l) => l.id) })}
            >
              {allSelected ? "Clear" : "Select all"}
            </button>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {all.map((l) => {
              const on = d.unit_ids.includes(l.id);
              return (
                <label key={l.id} className={cn("flex cursor-pointer items-center gap-3 rounded-xl border px-3.5 py-2.5 text-[14px] transition", on ? "border-ink" : "border-line-soft hover:border-ink-3")}>
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() => setD({ ...d, unit_ids: on ? d.unit_ids.filter((x) => x !== l.id) : [...d.unit_ids, l.id] })}
                    className="size-4 accent-ink"
                  />
                  <span className="truncate">{l.name}</span>
                </label>
              );
            })}
          </div>
          {errors.unit_ids && <p className="mt-1.5 text-[13px] text-danger">{errors.unit_ids}</p>}
          <p className="mt-2 flex items-center gap-1.5 text-[12.5px] text-ink-2">
            <Users className="size-3.5" /> Turnover cleans and maintenance jobs for these homes are sent to them.
          </p>
        </div>
        {isSelf && (
          <Tooltip content="You can't change your own role or deactivate yourself.">
            <p className="text-[12.5px] text-ink-3">Your own role and status are locked.</p>
          </Tooltip>
        )}
      </div>
    </DialogContent>
  );
}
