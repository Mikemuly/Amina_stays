"use client";

import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { Slot } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

// Airbnb's button geometry: 8px radius on small (32px) buttons, 12px on 40-56px ones, a pill for the
// primary action and circles for icon buttons. compoundVariants are emitted last, so tailwind-merge
// lets the brand pill win over the size radius.
const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-lg font-medium whitespace-nowrap transition-[transform,background-color,box-shadow,color,border-color] duration-200 ease-[cubic-bezier(.2,0,0,1)] select-none active:scale-[0.96] disabled:pointer-events-none disabled:opacity-40 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        brand: "btn-gradient text-white",
        dark: "bg-ink text-white hover:bg-black",
        outline: "border border-ink bg-white text-ink hover:bg-surface",
        soft: "bg-chip text-ink hover:bg-line-soft",
        ghost: "text-ink hover:bg-chip",
        ocean: "bg-ocean-600 text-white hover:bg-ocean-700",
        danger: "bg-danger text-white hover:brightness-95",
        "danger-outline": "border border-danger/40 bg-white text-danger hover:bg-danger-50",
        link: "px-0 font-semibold text-ink underline underline-offset-4 hover:text-black",
      },
      size: {
        sm: "h-8 rounded-lg px-3 text-[13px]",
        md: "h-10 rounded-xl px-4 text-sm",
        lg: "h-12 rounded-xl px-6 text-base",
        xl: "h-14 rounded-xl px-7 text-base",
        icon: "size-9 rounded-full",
        "icon-sm": "size-8 rounded-full",
      },
    },
    compoundVariants: [
      { variant: "brand", className: "rounded-full" },
      { variant: "link", className: "rounded-none" },
    ],
    defaultVariants: { variant: "dark", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, loading, children, onMouseMove, ...props }, ref) => {
    const Comp = asChild ? Slot.Root : "button";
    const track = (e: React.MouseEvent<HTMLButtonElement>) => {
      if (variant === "brand") {
        const r = e.currentTarget.getBoundingClientRect();
        e.currentTarget.style.setProperty("--x", `${((e.clientX - r.left) / r.width) * 100}%`);
        e.currentTarget.style.setProperty("--y", `${((e.clientY - r.top) / r.height) * 100}%`);
      }
      onMouseMove?.(e);
    };
    return (
      <Comp ref={ref} className={cn(buttonVariants({ variant, size }), className)} onMouseMove={track} disabled={props.disabled || loading} {...props}>
        {asChild ? (
          children
        ) : (
          <>
            {loading && <Loader2 className="size-4 animate-spin" />}
            {children}
          </>
        )}
      </Comp>
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };
