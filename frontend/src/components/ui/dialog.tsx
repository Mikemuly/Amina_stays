"use client";

import { X } from "lucide-react";
import { Dialog as D } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;

export function DialogContent({
  title, description, children, className, size = "md", footer, hideClose,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  size?: "sm" | "md" | "lg" | "xl" | "full";
  footer?: React.ReactNode;
  hideClose?: boolean;
}) {
  const width = { sm: "sm:max-w-md", md: "sm:max-w-xl", lg: "sm:max-w-3xl", xl: "sm:max-w-5xl", full: "sm:max-w-[1200px]" }[size];
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-50 bg-black/40 animate-fade-in" />
      <D.Content
        className={cn(
          "fixed inset-x-0 bottom-0 z-50 flex max-h-[92dvh] flex-col rounded-t-3xl bg-white shadow-float animate-slide-up outline-none",
          "sm:inset-auto sm:top-1/2 sm:left-1/2 sm:w-full sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-3xl",
          width,
          className,
        )}
      >
        {(title || !hideClose) && (
          <div className="relative flex min-h-16 shrink-0 items-center justify-center border-b border-line-soft px-14">
            {!hideClose && (
              <D.Close className="absolute left-4 grid size-8 place-items-center rounded-full hover:bg-surface" aria-label="Close">
                <X className="size-4" strokeWidth={2.4} />
              </D.Close>
            )}
            {title ? <D.Title className="text-base font-bold">{title}</D.Title> : <D.Title className="sr-only">Dialog</D.Title>}
          </div>
        )}
        {description ? <D.Description className="sr-only">{description}</D.Description> : <D.Description className="sr-only">{typeof title === "string" ? title : "Dialog"}</D.Description>}
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
        {footer && <div className="shrink-0 border-t border-line-soft px-6 py-4">{footer}</div>}
      </D.Content>
    </D.Portal>
  );
}

export function SheetContent({
  title, children, className, footer, side = "right", width = "max-w-xl",
}: { title?: React.ReactNode; children: React.ReactNode; className?: string; footer?: React.ReactNode; side?: "right" | "left"; width?: string }) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-50 bg-black/40 animate-fade-in" />
      <D.Content
        className={cn(
          "fixed inset-y-0 z-50 flex w-full flex-col bg-white shadow-float outline-none animate-slide-in-right",
          side === "right" ? "right-0" : "left-0",
          width,
          className,
        )}
      >
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-line-soft px-6">
          <D.Title className="truncate text-lg font-bold">{title}</D.Title>
          <D.Close className="grid size-9 place-items-center rounded-full hover:bg-surface" aria-label="Close">
            <X className="size-4" strokeWidth={2.4} />
          </D.Close>
        </div>
        <D.Description className="sr-only">{typeof title === "string" ? title : "Details"}</D.Description>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
        {footer && <div className="shrink-0 border-t border-line-soft px-6 py-4">{footer}</div>}
      </D.Content>
    </D.Portal>
  );
}
