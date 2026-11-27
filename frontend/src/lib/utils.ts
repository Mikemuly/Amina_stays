import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// Teach tailwind-merge our custom radius token so `rounded-card` overrides other radii cleanly.
const twMerge = extendTailwindMerge({ extend: { theme: { radius: ["card"] } } });

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function initials(name?: string | null) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

export const FLAGS: Record<string, string> = {
  KE: "🇰🇪", GB: "🇬🇧", DE: "🇩🇪", IT: "🇮🇹", US: "🇺🇸", FR: "🇫🇷", NL: "🇳🇱", IN: "🇮🇳", UG: "🇺🇬", TZ: "🇹🇿", PL: "🇵🇱",
  CN: "🇨🇳", AE: "🇦🇪", ZA: "🇿🇦", ES: "🇪🇸", CH: "🇨🇭", SE: "🇸🇪", BE: "🇧🇪", CA: "🇨🇦", AU: "🇦🇺", RW: "🇷🇼", ET: "🇪🇹",
};

export function flag(code?: string | null) {
  return code ? FLAGS[code.toUpperCase()] ?? "🌍" : "";
}

export const COUNTRIES: [string, string][] = [
  ["KE", "Kenya"], ["GB", "United Kingdom"], ["DE", "Germany"], ["IT", "Italy"], ["US", "United States"], ["FR", "France"],
  ["NL", "Netherlands"], ["IN", "India"], ["UG", "Uganda"], ["TZ", "Tanzania"], ["PL", "Poland"], ["CN", "China"],
  ["AE", "United Arab Emirates"], ["ZA", "South Africa"], ["ES", "Spain"], ["CH", "Switzerland"], ["SE", "Sweden"],
  ["BE", "Belgium"], ["CA", "Canada"], ["AU", "Australia"], ["RW", "Rwanda"], ["ET", "Ethiopia"],
];
