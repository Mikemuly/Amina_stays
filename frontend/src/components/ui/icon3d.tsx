import { cn } from "@/lib/utils";

// Microsoft Fluent Emoji 3D (MIT licence) — see README "Credits". Files live in public/3d.
export type Icon3DName =
  | "airplane" | "antenna" | "baby-bottle" | "bar-chart" | "beach" | "bed" | "broom" | "calendar" | "classical-building"
  | "clipboard" | "cooking" | "credit-card" | "croissant" | "desert-island" | "door" | "envelope" | "gear" | "globe"
  | "glowing-star" | "guests" | "homes" | "hot-beverage" | "hotel" | "house" | "hut" | "key" | "kitchen" | "label" | "light-bulb"
  | "lock" | "megaphone" | "mobile-phone" | "money-bag" | "old-key" | "palm-tree" | "party-popper" | "pushpin" | "sailboat"
  | "services" | "shield" | "shopping-cart" | "siren" | "sparkles" | "speech-balloon" | "spiral-calendar" | "sponge" | "star"
  | "sunrise" | "sunset" | "test-tube" | "tools" | "train" | "trophy" | "tropical-fish" | "wave" | "wifi";

export function Icon3D({ name, size = 32, className, alt = "", eager }: { name: Icon3DName; size?: number; className?: string; alt?: string; eager?: boolean }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`/3d/${name}.png`}
      width={size}
      height={size}
      alt={alt}
      aria-hidden={alt ? undefined : true}
      draggable={false}
      loading={eager ? "eager" : "lazy"}
      decoding="async"
      className={cn("inline-block shrink-0 object-contain select-none", className)}
    />
  );
}
