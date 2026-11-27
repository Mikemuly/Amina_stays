"use client";

import { Stepper } from "@/components/ui/misc";

export type Guests = { adults: number; children: number; infants: number };

export function guestsLabel(g: Guests) {
  const n = g.adults + g.children;
  if (!n) return "Add guests";
  return `${n} guest${n !== 1 ? "s" : ""}${g.infants ? `, ${g.infants} infant${g.infants !== 1 ? "s" : ""}` : ""}`;
}

export function GuestPicker({ value, onChange, max = 16 }: { value: Guests; onChange: (g: Guests) => void; max?: number }) {
  const total = value.adults + value.children;
  const rows: { key: keyof Guests; label: string; hint: string; min: number; max: number }[] = [
    { key: "adults", label: "Adults", hint: "Ages 13 or above", min: 1, max: max - value.children },
    { key: "children", label: "Children", hint: "Ages 2–12", min: 0, max: max - value.adults },
    { key: "infants", label: "Infants", hint: "Under 2 · free, cot on request", min: 0, max: 4 },
  ];
  return (
    <div className="divide-y divide-line-soft">
      {rows.map((r) => (
        <div key={r.key} className="flex items-center justify-between gap-8 py-5">
          <div>
            <p className="font-medium">{r.label}</p>
            <p className="text-sm text-ink-2">{r.hint}</p>
          </div>
          <Stepper value={value[r.key]} min={r.min} max={r.max} label={r.label.toLowerCase()} onChange={(v) => onChange({ ...value, [r.key]: v })} />
        </div>
      ))}
      {total >= max && <p className="pt-3 text-[13px] text-ink-2">Our largest home sleeps {max}. For bigger groups, message Amina.</p>}
    </div>
  );
}
