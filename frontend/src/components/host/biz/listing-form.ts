// Listing editor form model: API ⇄ form conversion, dirty diffing and section/field mapping.

import type { AccessMethod, CancellationPolicy, Highlight, HostListing, ListingStatus, Sleeping } from "./types";

export interface ListingForm {
  name: string;
  area: string;
  property_type: string;
  summary: string;
  description: string;
  the_space: string;
  guest_access: string;
  neighbourhood: string;
  bedrooms: number;
  beds: number;
  bathrooms: string;
  max_guests: number;
  size_sqm: number | null;
  sleeping: Sleeping[];
  highlights: Highlight[];
  tags: string[];
  status: ListingStatus;
  is_featured: boolean;
  base_price: number | null;
  weekend_price: number | null;
  cleaning_fee: number | null;
  weekly_discount: number | null;
  monthly_discount: number | null;
  min_nights: number | null;
  max_nights: number | null;
  cancellation_policy: CancellationPolicy;
  checkin_time: string;
  checkout_time: string;
  amenity_codes: string[];
  house_rules: string[];
  pets_allowed: boolean;
  smoking_allowed: boolean;
  events_allowed: boolean;
  quiet_hours: string;
  safety_features: string[];
  breakfast_available: boolean;
  access_method: AccessMethod;
  lock_device_id: string;
  wifi_name: string;
  wifi_password: string;
  address: string;
  directions: string;
  landmark: string;
  map_link: string;
  latitude: number | null;
  longitude: number | null;
  parking: string;
  house_manual: string;
  local_tips: string;
  tra_licence_number: string;
}

export type FormKey = keyof ListingForm;
export type SetField = <K extends FormKey>(key: K, value: ListingForm[K]) => void;

export interface SectionProps {
  draft: ListingForm;
  set: SetField;
  errors: Record<string, string>;
}

export const SECTION_FIELDS: Record<string, FormKey[]> = {
  details: [
    "name", "area", "property_type", "summary", "description", "the_space", "guest_access", "neighbourhood", "bedrooms", "beds", "bathrooms",
    "max_guests", "size_sqm", "sleeping", "highlights", "tags", "status", "is_featured",
  ],
  photos: [],
  pricing: [
    "base_price", "weekend_price", "cleaning_fee", "weekly_discount", "monthly_discount", "min_nights", "max_nights", "cancellation_policy",
    "checkin_time", "checkout_time",
  ],
  amenities: ["amenity_codes"],
  rules: ["house_rules", "pets_allowed", "smoking_allowed", "events_allowed", "quiet_hours", "safety_features", "breakfast_available"],
  access: [
    "access_method", "lock_device_id", "wifi_name", "wifi_password", "address", "directions", "landmark", "map_link", "latitude", "longitude",
    "parking", "house_manual", "local_tips", "tra_licence_number",
  ],
  calendar: [],
};

const FORM_KEYS = Object.values(SECTION_FIELDS).flat();

const num = (v: string | null | undefined) => (v === null || v === undefined || v === "" ? null : Number(v));

export function toForm(l: HostListing): ListingForm {
  return {
    name: l.name, area: l.area, property_type: l.property_type, summary: l.summary, description: l.description, the_space: l.the_space,
    guest_access: l.guest_access, neighbourhood: l.neighbourhood, bedrooms: l.bedrooms, beds: l.beds, bathrooms: String(Number(l.bathrooms)),
    max_guests: l.max_guests, size_sqm: l.size_sqm, sleeping: l.sleeping ?? [], highlights: l.highlights ?? [], tags: l.tags ?? [],
    status: l.status, is_featured: l.is_featured, base_price: l.base_price, weekend_price: l.weekend_price, cleaning_fee: l.cleaning_fee,
    weekly_discount: l.weekly_discount, monthly_discount: l.monthly_discount, min_nights: l.min_nights, max_nights: l.max_nights,
    cancellation_policy: l.cancellation_policy, checkin_time: l.checkin_time, checkout_time: l.checkout_time, amenity_codes: l.amenity_codes ?? [],
    house_rules: l.house_rules ?? [], pets_allowed: l.pets_allowed, smoking_allowed: l.smoking_allowed, events_allowed: l.events_allowed,
    quiet_hours: l.quiet_hours, safety_features: l.safety_features ?? [], breakfast_available: l.breakfast_available, access_method: l.access_method,
    lock_device_id: l.lock_device_id, wifi_name: l.wifi_name, wifi_password: l.wifi_password, address: l.address, directions: l.directions,
    landmark: l.landmark, map_link: l.map_link, latitude: num(l.latitude), longitude: num(l.longitude), parking: l.parking,
    house_manual: l.house_manual, local_tips: l.local_tips, tra_licence_number: l.tra_licence_number,
  };
}

export function blankForm(area: string): ListingForm {
  return {
    name: "", area, property_type: "apartment", summary: "", description: "", the_space: "", guest_access: "", neighbourhood: "",
    bedrooms: 1, beds: 1, bathrooms: "1", max_guests: 2, size_sqm: null, sleeping: [{ room: "Bedroom 1", beds: "1 queen bed" }], highlights: [],
    tags: [], status: "draft", is_featured: false, base_price: null, weekend_price: null, cleaning_fee: 0, weekly_discount: 0, monthly_discount: 0,
    min_nights: 1, max_nights: 60, cancellation_policy: "moderate", checkin_time: "", checkout_time: "", amenity_codes: [],
    house_rules: ["No parties or events", "No smoking indoors", "Registered guests only - ID or passport for every adult"], pets_allowed: false,
    smoking_allowed: false, events_allowed: false, quiet_hours: "22:00–07:00", safety_features: ["Smoke alarm", "Fire extinguisher", "First-aid kit"],
    breakfast_available: true, access_method: "simulated", lock_device_id: "", wifi_name: "", wifi_password: "", address: "", directions: "",
    landmark: "", map_link: "", latitude: null, longitude: null, parking: "", house_manual: "", local_tips: "", tra_licence_number: "",
  };
}

const trimList = (xs: string[]) => xs.map((x) => x.trim()).filter(Boolean);
const coord = (v: number | null) => (v === null || Number.isNaN(v) ? null : Number(v.toFixed(6)));

/** The JSON the API receives for a form (normalised, so diffing ignores cosmetic differences). */
export function toPayload(f: ListingForm): Record<FormKey, unknown> {
  return {
    ...f,
    name: f.name.trim(),
    summary: f.summary.trim(),
    sleeping: f.sleeping.map((s) => ({ room: s.room.trim(), beds: s.beds.trim() })).filter((s) => s.room || s.beds),
    highlights: f.highlights.map((h) => ({ icon: h.icon, title: h.title.trim(), text: h.text.trim() })).filter((h) => h.title || h.text),
    house_rules: trimList(f.house_rules),
    safety_features: trimList(f.safety_features),
    amenity_codes: [...f.amenity_codes].sort(),
    tags: [...f.tags].sort(),
    latitude: coord(f.latitude),
    longitude: coord(f.longitude),
  };
}

export function changedKeys(base: ListingForm, draft: ListingForm): FormKey[] {
  const a = toPayload(base);
  const b = toPayload(draft);
  return FORM_KEYS.filter((k) => JSON.stringify(a[k]) !== JSON.stringify(b[k]));
}

export function sectionOf(field: string) {
  return Object.entries(SECTION_FIELDS).find(([, fields]) => (fields as string[]).includes(field))?.[0];
}

export const POLICY_TEXT: Record<CancellationPolicy, string> = {
  flexible: "Free cancellation until 24 hours before check-in.",
  moderate: "Free cancellation until 5 days before check-in, then 50% back.",
  firm: "Full refund until 30 days before check-in, 50% until 7 days before.",
  strict: "50% refund until 7 days before check-in.",
};

export const ACCESS_METHODS: { value: AccessMethod; title: string; text: string }[] = [
  { value: "simulated", title: "Simulated keypad", text: "Demo keypad on the console lock panel — codes work exactly like a smart lock." },
  { value: "igloohome", title: "igloohome", text: "Offline algoPIN codes — no Wi-Fi needed at the door." },
  { value: "ttlock", title: "TTLock", text: "Time-limited passcodes created through the TTLock cloud." },
  { value: "nuki", title: "Nuki", text: "Keypad codes for Nuki smart locks." },
  { value: "lockbox", title: "Key lockbox", text: "Guests get the lockbox code on arrival morning." },
  { value: "caretaker", title: "Caretaker hands over keys", text: "No code — the caretaker meets guests (ETA matters)." },
];

export const PROPERTY_TYPES = ["apartment", "studio", "villa", "cottage", "penthouse", "house", "room"];

export const LISTING_TAGS = [
  "beachfront", "pool", "family", "workspace", "historic", "budget", "couples", "creek", "nature", "garden", "groups", "ocean-view", "breakfast", "near-beach",
];

export const HIGHLIGHT_ICONS = [
  "waves", "sun", "sunset", "sunrise", "umbrella", "sailboat", "trees", "key-round", "laptop", "wifi", "zap", "battery-charging", "air-vent",
  "coffee", "croissant", "chef-hat", "utensils", "shield-check", "lock", "cctv", "map-pin", "landmark", "plane", "train-front", "square-parking",
  "baby", "bed", "sparkles", "droplets", "flame", "accessibility", "book-open", "building-2", "shopping-basket",
];

export const PHOTO_ROOMS = ["exterior", "living", "bedroom", "kitchen", "bathroom", "view", "pool", "dining", "other"];

export const BATHROOM_OPTIONS = ["0.5", "1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5", "6", "7", "8"];
