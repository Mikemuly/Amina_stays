"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

const field =
  "w-full rounded-lg border border-line bg-white px-3.5 text-[15px] text-ink placeholder:text-ink-3 transition-colors outline-none focus:border-ink focus:ring-1 focus:ring-ink disabled:bg-surface disabled:text-ink-3";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => (
  <input ref={ref} className={cn(field, "h-11", className)} {...props} />
));
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => <textarea ref={ref} className={cn(field, "min-h-24 py-2.5 leading-relaxed", className)} {...props} />,
);
Textarea.displayName = "Textarea";

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(({ className, children, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      field,
      "h-11 appearance-none bg-[url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='none' stroke='%23222' stroke-width='2'%3E%3Cpath d='m4 6 4 4 4-4'/%3E%3C/svg%3E\")] bg-[right_12px_center] bg-no-repeat pr-9",
      className,
    )}
    {...props}
  >
    {children}
  </select>
));
Select.displayName = "Select";

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("mb-1.5 block text-[13px] font-semibold text-ink", className)} {...props} />;
}

type ControlProps = { id?: string; "aria-describedby"?: string; "aria-invalid"?: boolean | "true" | "false" };

const LABELLABLE = new Set<unknown>([Input, Textarea, Select, "input", "select", "textarea"]);

/** Label + control + hint/error. A single child control gets an id so the label, hint and error are announced with it. */
export function Field({
  label, hint, error, children, className,
}: { label?: React.ReactNode; hint?: React.ReactNode; error?: React.ReactNode; children: React.ReactNode; className?: string }) {
  const autoId = React.useId();
  const child = React.isValidElement<ControlProps>(children) && LABELLABLE.has(children.type) ? children : null;
  const id = child?.props.id ?? autoId;
  const descId = `${id}-desc`;
  const note = error || hint;
  const control = child
    ? React.cloneElement(child, {
        id,
        "aria-describedby": [child.props["aria-describedby"], note ? descId : null].filter(Boolean).join(" ") || undefined,
        "aria-invalid": error ? true : child.props["aria-invalid"],
      })
    : children;
  return (
    <div className={className}>
      {label && <Label htmlFor={child ? id : undefined}>{label}</Label>}
      {control}
      {error ? <p id={descId} className="mt-1.5 text-[13px] text-danger">{error}</p> : hint ? <p id={descId} className="mt-1.5 text-[13px] text-ink-2">{hint}</p> : null}
    </div>
  );
}
