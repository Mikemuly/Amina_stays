"use client";

import { ArrowRight, ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { cn } from "@/lib/utils";

// How many cards fit per breakpoint (gap 12px). Underscores keep the calc() operators spaced.
const COLS = {
  homes:
    "auto-cols-[44%] sm:auto-cols-[calc((100%_-_24px)/3)] md:auto-cols-[calc((100%_-_36px)/4)] lg:auto-cols-[calc((100%_-_48px)/5)] min-[1128px]:auto-cols-[calc((100%_-_60px)/6)] min-[1400px]:auto-cols-[calc((100%_-_72px)/7)]",
  tiles:
    "auto-cols-[31%] sm:auto-cols-[calc((100%_-_48px)/5)] md:auto-cols-[calc((100%_-_72px)/7)] lg:auto-cols-[calc((100%_-_96px)/9)] min-[1128px]:auto-cols-[calc((100%_-_108px)/10)]",
  wide: "auto-cols-[82%] sm:auto-cols-[calc((100%_-_12px)/2)] md:auto-cols-[calc((100%_-_24px)/3)] xl:auto-cols-[calc((100%_-_36px)/4)]",
};

export function CarouselRow({ title, subtitle, href, cols = "homes", children, className }: {
  title: string;
  subtitle?: string;
  href?: string;
  cols?: keyof typeof COLS;
  children: React.ReactNode;
  className?: string;
}) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [edge, setEdge] = React.useState({ start: true, end: true });
  const measure = React.useCallback(() => {
    const el = ref.current;
    if (!el) return;
    setEdge({ start: el.scrollLeft <= 4, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 4 });
  }, []);
  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [measure]);
  const page = (d: number) => ref.current?.scrollBy({ left: d * (ref.current.clientWidth - 40), behavior: "smooth" });

  const heading = (
    <h2 className="text-lg leading-6 font-semibold tracking-[-0.18px] md:text-xl">
      {title}
    </h2>
  );
  return (
    <section className={cn("pt-8 md:pt-10", className)}>
      <div className="mb-3 flex items-center justify-between gap-4">
        <div className="min-w-0">
          {href ? (
            <Link href={href} className="group inline-flex items-center gap-2">
              {heading}
              <span className="grid size-7 place-items-center rounded-full bg-chip transition-colors group-hover:bg-line-soft">
                <ArrowRight className="size-3.5" strokeWidth={2.6} />
              </span>
            </Link>
          ) : (
            heading
          )}
          {subtitle && <p className="mt-0.5 text-sm text-ink-2">{subtitle}</p>}
        </div>
        {!(edge.start && edge.end) && (
          <div className="hidden shrink-0 gap-2 md:flex">
            <PagerButton dir={-1} disabled={edge.start} onClick={() => page(-1)} />
            <PagerButton dir={1} disabled={edge.end} onClick={() => page(1)} />
          </div>
        )}
      </div>
      <div
        ref={ref}
        onScroll={measure}
        className={cn("no-scrollbar -mx-6 grid snap-x snap-mandatory scroll-px-6 grid-flow-col gap-3 overflow-x-auto px-6 md:mx-0 md:scroll-px-0 md:px-0", COLS[cols])}
      >
        {React.Children.map(children, (child) => child && <div className="snap-start">{child}</div>)}
      </div>
    </section>
  );
}

function PagerButton({ dir, disabled, onClick }: { dir: 1 | -1; disabled: boolean; onClick: () => void }) {
  const Icon = dir === 1 ? ChevronRight : ChevronLeft;
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={dir === 1 ? "Next" : "Previous"}
      className="grid size-7 place-items-center rounded-full bg-chip transition-[background-color,opacity] hover:bg-line-soft disabled:cursor-default disabled:opacity-40 disabled:hover:bg-chip"
    >
      <Icon className="size-3.5" strokeWidth={2.6} />
    </button>
  );
}
