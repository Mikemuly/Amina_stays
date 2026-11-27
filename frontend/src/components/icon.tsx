import {
  Accessibility, AirVent, AlarmSmoke, Armchair, ArrowUpDown, Baby, BatteryCharging, Bed, BookOpen, Building2, BriefcaseMedical, BugOff, Cctv,
  Check, ChefHat, Clapperboard, Coffee, CookingPot, Croissant, Droplets, Fan, FireExtinguisher, Flame, KeyRound, Landmark, Laptop, Lock,
  type LucideIcon, type LucideProps, MapPin, Microwave, Plane, Refrigerator, Sailboat, ShieldCheck, Shirt, ShoppingBasket, ShowerHead,
  Sparkles, SquareParking, Sun, Sunrise, Sunset, TrainFront, Trees, Tv, Umbrella, Utensils, WashingMachine, Waves, Wifi, Wind, Zap,
} from "lucide-react";

// Icon names stored in the database (kebab-case lucide names) → components.
const ICONS: Record<string, LucideIcon> = {
  accessibility: Accessibility, "air-vent": AirVent, "alarm-smoke": AlarmSmoke, armchair: Armchair, "arrow-up-down": ArrowUpDown, baby: Baby,
  "battery-charging": BatteryCharging, bed: Bed, "book-open": BookOpen, "building-2": Building2, "briefcase-medical": BriefcaseMedical,
  "bug-off": BugOff, cctv: Cctv, check: Check, "chef-hat": ChefHat, clapperboard: Clapperboard, coffee: Coffee, "cooking-pot": CookingPot,
  croissant: Croissant, droplets: Droplets, fan: Fan, "fire-extinguisher": FireExtinguisher, flame: Flame, "key-round": KeyRound, landmark: Landmark,
  laptop: Laptop, lock: Lock, "map-pin": MapPin, microwave: Microwave, plane: Plane, refrigerator: Refrigerator, sailboat: Sailboat,
  "shield-check": ShieldCheck, shirt: Shirt, "shopping-basket": ShoppingBasket, "shower-head": ShowerHead, sparkles: Sparkles,
  "square-parking": SquareParking, sun: Sun, sunrise: Sunrise, sunset: Sunset, "train-front": TrainFront, trees: Trees, tv: Tv, umbrella: Umbrella,
  utensils: Utensils, "washing-machine": WashingMachine, waves: Waves, wifi: Wifi, wind: Wind, zap: Zap,
};

export function Icon({ name, ...props }: { name?: string } & LucideProps) {
  const C = (name && ICONS[name]) || Check;
  return <C strokeWidth={1.6} {...props} />;
}
