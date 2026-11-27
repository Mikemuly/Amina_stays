"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Delete, KeyRound, Lock, LockOpen, ShieldX } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { ErrorBlock, Section } from "@/components/host/common";
import { Button } from "@/components/ui/button";
import { Badge, Skeleton } from "@/components/ui/misc";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/overlays";
import { get, post } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { cn } from "@/lib/utils";

import { HousekeepingChip, OpsKeyframes } from "./bits";
import { relTime, useNow } from "./lib";
import type { LockRow } from "./types";

const group = (code: string) => (code.length > 4 ? code.replace(/(\d{3})(?=\d)/g, "$1 ") : code);

export function DoorLocksPanel() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["host", "ops", "locks"],
    queryFn: () => get<LockRow[]>("/api/host/locks"),
    refetchInterval: 5_000,
  });
  const occupied = data?.filter((l) => l.state === "occupied").length ?? 0;

  return (
    <Section
      padded={false}
      title={
        <span className="flex items-center gap-2">
          <KeyRound className="size-4 text-ink-2" /> Door locks
        </span>
      }
      action={data && <span className="text-[13px] text-ink-2 tabular-nums">{occupied} occupied · {data.length - occupied} vacant</span>}
    >
      <OpsKeyframes />
      {isLoading ? (
        <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-52 rounded-2xl" />
          ))}
        </div>
      ) : error ? (
        <div className="p-4">
          <ErrorBlock error={error} retry={() => refetch()} />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 xl:grid-cols-3">
          {data?.map((l) => <LockCard key={l.unit.id} lock={l} />)}
        </div>
      )}
    </Section>
  );
}

function LockCard({ lock }: { lock: LockRow }) {
  const now = useNow(30_000);
  const { unit, active, next } = lock;
  const occupied = lock.state === "occupied";
  return (
    <div className="flex flex-col rounded-2xl border border-line-soft p-4 transition-shadow hover:shadow-soft">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-bold">{unit.name}</p>
          <p className="truncate text-xs text-ink-2">{unit.area}</p>
        </div>
        <Badge tone={occupied ? "ocean" : "neutral"} dot>
          {occupied ? "Occupied" : "Vacant"}
        </Badge>
      </div>

      <div
        className={cn(
          "mt-3 flex h-16 items-center justify-center rounded-xl font-mono text-[28px] leading-none font-semibold tracking-[0.18em] tabular-nums",
          occupied ? "bg-ink text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.08)]" : "bg-surface text-ink-3",
        )}
        aria-label={active ? `Active code ${active.code.split("").join(" ")}` : "No active code"}
      >
        {active ? group(active.code) : "– – – – – –"}
      </div>

      <div className="mt-3 min-h-10 space-y-0.5 text-[13px]">
        {active ? (
          <>
            <p className="truncate">
              <Link href={`/host/reservations/${active.ref}`} className="font-semibold hover:underline">
                {active.guest}
              </Link>
              <span className="text-ink-2"> · until {fmtDate(active.valid_until, "EEE h:mmaaa")}</span>
            </p>
            <p className="truncate text-ink-2">{active.last_used_at ? `Last opened ${relTime(active.last_used_at, now)}` : "Not used yet"}</p>
          </>
        ) : (
          <p className="text-ink-2">No guest code active</p>
        )}
        {next && (
          <p className="truncate text-ink-2">
            Next:{" "}
            <Link href={`/host/reservations/${next.ref}`} className="font-medium text-ink hover:underline">
              {next.ref}
            </Link>{" "}
            from {fmtDate(next.valid_from, "EEE d MMM, h:mmaaa")}
          </p>
        )}
      </div>

      <div className="mt-auto flex items-center justify-between gap-2 pt-3">
        <div className="flex min-w-0 items-center gap-2">
          <HousekeepingChip status={unit.housekeeping} />
        </div>
        <KeypadTester lock={lock} />
      </div>
      <p className="mt-2 flex items-center gap-1 truncate text-[11px] text-ink-3">
        <Lock className="size-3" /> {unit.provider}
      </p>
    </div>
  );
}

type Result = { ok: boolean; ref: string | null; attempt: number };

function KeypadTester({ lock }: { lock: LockRow }) {
  const qc = useQueryClient();
  const [open, setOpen] = React.useState(false);
  const [code, setCode] = React.useState("");
  const [result, setResult] = React.useState<Result | null>(null);

  const test = useMutation({
    mutationFn: (c: string) => post<{ unlocked: boolean; ref: string | null }>("/api/host/locks", { unit: lock.unit.id, code: c }),
    onSuccess: (r) => {
      setResult((prev) => ({ ok: r.unlocked, ref: r.ref, attempt: (prev?.attempt ?? 0) + 1 }));
      if (r.unlocked) qc.invalidateQueries({ queryKey: ["host", "ops"] });
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const press = (key: string) => {
    if (test.isPending) return;
    if (key === "back") setCode((c) => c.slice(0, -1));
    else if (key === "clear") setCode("");
    else setCode((c) => (c.length >= 10 ? c : c + key));
    setResult(null);
  };
  const submit = () => {
    if (code.length >= 4) test.mutate(code);
  };

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) {
          setCode("");
          setResult(null);
        }
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="soft" size="sm">
          <KeyRound className="size-3.5" /> Test code
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-[272px] p-4"
        onKeyDown={(e) => {
          if (/^\d$/.test(e.key)) press(e.key);
          else if (e.key === "Backspace") press("back");
          else if (e.key === "Enter") {
            e.preventDefault();
            submit();
          }
        }}
      >
        <p className="text-sm font-bold">{lock.unit.name} keypad</p>
        <p className="text-xs text-ink-2">Type a code as a guest would at the door.</p>

        <div
          key={result?.attempt}
          className={cn(
            "mt-3 flex h-14 items-center justify-center rounded-xl font-mono text-2xl font-semibold tracking-[0.3em] tabular-nums transition-colors",
            result ? (result.ok ? "bg-success text-white" : "bg-danger text-white") : "bg-ink text-white",
          )}
          style={result ? { animation: result.ok ? "ops-pop .35s ease-out" : "ops-shake .45s ease-in-out" } : undefined}
          aria-live="polite"
        >
          {result ? (
            <span className="flex items-center gap-2 font-sans text-base tracking-normal">
              {result.ok ? <LockOpen className="size-5" /> : <ShieldX className="size-5" />}
              {result.ok ? "Unlocked ✓" : "Wrong code ✗"}
            </span>
          ) : code ? (
            code
          ) : (
            <span className="text-white/30">••••••</span>
          )}
        </div>
        {result?.ok && result.ref && <p className="mt-1.5 text-center text-xs text-success">Opened with {result.ref}&apos;s code · logged to the feed</p>}

        <div className="mt-3 grid grid-cols-3 gap-2">
          {["1", "2", "3", "4", "5", "6", "7", "8", "9", "clear", "0", "back"].map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => press(k)}
              aria-label={k === "back" ? "Delete digit" : k === "clear" ? "Clear" : k}
              className="grid h-11 place-items-center rounded-xl border border-line-soft bg-white text-lg font-semibold tabular-nums transition hover:bg-surface active:scale-95"
            >
              {k === "back" ? <Delete className="size-4.5" /> : k === "clear" ? <span className="text-xs font-bold text-ink-2">CLR</span> : k}
            </button>
          ))}
        </div>
        <Button className="mt-3 w-full" variant="dark" loading={test.isPending} disabled={code.length < 4} onClick={submit}>
          Unlock
        </Button>
        {lock.active && (
          <button
            type="button"
            className="mt-2 w-full text-center text-xs font-semibold text-ink-2 hover:text-ink"
            onClick={() => {
              setCode(lock.active!.code);
              setResult(null);
            }}
          >
            Fill {lock.active.guest.split(" ")[0]}&apos;s code
          </button>
        )}
      </PopoverContent>
    </Popover>
  );
}
