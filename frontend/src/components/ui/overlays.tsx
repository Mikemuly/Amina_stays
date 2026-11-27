"use client";

import { DropdownMenu as DM, Popover as P, Switch as S, Tabs as T, Tooltip as TT } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

// ---------- Popover ----------
export const Popover = P.Root;
export const PopoverTrigger = P.Trigger;
export const PopoverAnchor = P.Anchor;
export function PopoverContent({ className, align = "center", sideOffset = 10, ...props }: React.ComponentProps<typeof P.Content>) {
  return (
    <P.Portal>
      <P.Content
        align={align}
        sideOffset={sideOffset}
        className={cn("z-50 max-h-[var(--radix-popover-content-available-height)] overflow-y-auto rounded-2xl border border-line-soft bg-white p-4 shadow-float outline-none animate-fade-in", className)}
        {...props}
      />
    </P.Portal>
  );
}

// ---------- Dropdown ----------
export const Dropdown = DM.Root;
export const DropdownTrigger = DM.Trigger;
export function DropdownContent({ className, align = "end", ...props }: React.ComponentProps<typeof DM.Content>) {
  return (
    <DM.Portal>
      <DM.Content
        align={align}
        sideOffset={8}
        className={cn("z-50 max-h-[var(--radix-dropdown-menu-content-available-height)] min-w-56 overflow-y-auto rounded-xl border border-line-soft bg-white py-2 shadow-float outline-none animate-fade-in", className)}
        {...props}
      />
    </DM.Portal>
  );
}
export function DropdownItem({ className, ...props }: React.ComponentProps<typeof DM.Item>) {
  return (
    <DM.Item
      className={cn("flex cursor-pointer items-center gap-3 px-4 py-2.5 text-sm outline-none data-[highlighted]:bg-surface", className)}
      {...props}
    />
  );
}
export const DropdownSeparator = ({ className }: { className?: string }) => <DM.Separator className={cn("my-2 h-px bg-line-soft", className)} />;

// ---------- Tabs ----------
export const Tabs = T.Root;
export function TabsList({ className, ...props }: React.ComponentProps<typeof T.List>) {
  return <T.List className={cn("flex gap-6 border-b border-line-soft", className)} {...props} />;
}
export function TabsTrigger({ className, ...props }: React.ComponentProps<typeof T.Trigger>) {
  return (
    <T.Trigger
      className={cn(
        "-mb-px border-b-2 border-transparent pb-3 text-sm font-semibold text-ink-2 transition-colors hover:text-ink data-[state=active]:border-ink data-[state=active]:text-ink",
        className,
      )}
      {...props}
    />
  );
}
export const TabsContent = T.Content;

// ---------- Switch ----------
export function Switch({ className, ...props }: React.ComponentProps<typeof S.Root>) {
  return (
    <S.Root
      className={cn(
        "relative inline-flex h-7 w-12 shrink-0 cursor-pointer items-center rounded-full bg-line transition-colors data-[state=checked]:bg-ink disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <S.Thumb className="ml-0.5 block size-6 rounded-full bg-white shadow-sm transition-transform data-[state=checked]:translate-x-5" />
    </S.Root>
  );
}

// ---------- Tooltip ----------
export function Tooltip({ content, children, side = "top" }: { content: React.ReactNode; children: React.ReactNode; side?: "top" | "bottom" | "left" | "right" }) {
  return (
    <TT.Provider delayDuration={200}>
      <TT.Root>
        <TT.Trigger asChild>{children}</TT.Trigger>
        <TT.Portal>
          <TT.Content side={side} sideOffset={6} className="z-50 max-w-xs rounded-lg bg-ink px-2.5 py-1.5 text-xs font-medium text-white shadow-md animate-fade-in">
            {content}
          </TT.Content>
        </TT.Portal>
      </TT.Root>
    </TT.Provider>
  );
}
