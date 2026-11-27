import Link from "next/link";

import { cn } from "@/lib/utils";

/** The Amina mark: a dhow's lateen sail riding an Indian Ocean wave. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-8 text-brand-500", className)} fill="none" aria-hidden>
      <path d="M7.5 19.5 17.2 3.4c.3-.5 1-.5 1.3 0 3 5 5.4 10 7 15.3.2.5-.2.8-.7.8H7.5Z" fill="currentColor" />
      <path d="M16.6 4.4v15" stroke="#fff" strokeWidth="1.4" strokeLinecap="round" opacity=".55" />
      <path d="M3 25.2c2.2-1.6 4.4-1.6 6.5 0s4.3 1.6 6.5 0 4.3-1.6 6.5 0 4.3 1.6 6.5 0" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
    </svg>
  );
}

export function BrandLink({ className, compact }: { className?: string; compact?: boolean }) {
  return (
    <Link href="/" className={cn("flex shrink-0 items-center gap-1.5 text-brand-500", className)} aria-label="Amina Stays home">
      <BrandMark className="size-[34px]" />
      <span className={cn("text-[21px] leading-none font-extrabold tracking-[-0.04em]", compact && "hidden lg:inline")}>amina stays</span>
    </Link>
  );
}
