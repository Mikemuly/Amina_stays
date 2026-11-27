// API response shapes (mirrors the Django serializers in backend/apps/*/serializers.py & views.py).

export type Lang = "en" | "sw" | "it" | "de" | "fr";

export interface Config {
  business: { name: string; host_name: string; tagline: string; email: string; tra_licence: string; checkin_time: string; checkout_time: string };
  channels: { ussd_code: string; sms_number: string; voice_number: string; whatsapp: string };
  payments: { mpesa: "off" | "simulate" | "daraja" | "africastalking"; card: "simulate" | "stripe" | "paystack"; simulated: boolean; card_test_mode?: boolean };
  paybill?: { number: string; account_hint: string } | null;
  currencies: Record<string, number>;
  deposit_percent: number;
  hold_minutes: number;
  levy_percent: number;
  require_id: boolean;
  demo: boolean;
  sandbox: boolean;
  emergency: Record<string, string>;
  demo_lab?: {
    host_phone: string;
    host_name: string;
    guests: DemoPersona[];
    staff: DemoPersona[];
  };
}

export interface DemoPersona {
  phone: string;
  name: string;
  role: string;
  lang: string;
  ref: string | null;
  note: string;
}

export interface Me {
  authenticated: boolean;
  id?: number;
  phone?: string;
  name?: string;
  email?: string;
  role?: string;
  is_host?: boolean;
  lang?: Lang;
  nationality?: string;
  preferred_channel?: "sms" | "whatsapp";
  marketing_opt_in?: boolean;
  identity?: { type: string; type_label: string; last4: string; submitted_at: string | null; verified: boolean };
  languages?: [string, string][];
  id_types?: [string, string][];
}

export interface Area {
  name: string;
  slug: string;
  summary: string;
  description: string;
  photo_url: string;
  getting_there: string;
  units_count: number | null;
  location: { lat: number; lng: number } | null;
}

export interface ListingCard {
  id: number;
  slug: string;
  name: string;
  headline: string;
  summary: string;
  property_type: string;
  area: { name: string; slug: string };
  bedrooms: number;
  beds: number;
  bathrooms: number;
  max_guests: number;
  photos: string[];
  tags: string[];
  is_featured: boolean;
  rating: number | null;
  reviews_count: number;
  guest_favourite: boolean;
  location: { lat: number; lng: number } | null;
  wishlisted: boolean;
  breakfast_available: boolean;
  free_cancellation: boolean;
  price: { from_nightly: number; base_price: number; total?: number; nights?: number; avg_nightly?: number };
}

export interface Addon {
  code: string;
  name: string;
  short: string;
  description: string;
  category: string;
  icon: string;
  photo_url: string;
  price: number;
  pricing: string;
  pricing_label: string;
  requires_approval: boolean;
  options: { styles?: string[]; hours?: string; default_time?: string; dietary?: string[]; time?: string; fields?: string[] };
}

export interface ListingDetail extends Omit<ListingCard, "photos"> {
  description: string;
  the_space: string;
  guest_access: string;
  neighbourhood: string;
  sleeping: { room: string; beds: string }[];
  size_sqm: number | null;
  photos: { src: string; caption: string; room: string }[];
  amenities: { code: string; name: string; icon: string; category: string }[];
  highlights: { icon: string; title: string; text: string }[];
  house_rules: string[];
  pets_allowed: boolean;
  smoking_allowed: boolean;
  events_allowed: boolean;
  quiet_hours: string;
  safety_features: string[];
  checkin_time: string;
  checkout_time: string;
  access_method: string;
  self_checkin: boolean;
  min_nights: number;
  max_nights: number;
  cleaning_fee: number;
  weekend_price: number | null;
  weekly_discount: number;
  monthly_discount: number;
  cancellation: { policy: string; label: string; text: string };
  reviews_summary: { rating: number | null; count: number; categories: Record<string, number>; guest_favourite: boolean };
  area_info: { name: string; summary: string; description: string; getting_there: string; photo_url: string };
  host: { name: string; since: number; response_time: string; languages: string[]; superhost: boolean; verified: boolean };
  addons: Addon[];
  tra_licence: string;
  levy_percent: number;
  deposit_percent: number;
}

export interface QuoteLine {
  label: string;
  amount: number;
  kind?: string;
}

export interface Quote {
  nights: number;
  nightly: { date: string; price: number; label: string }[];
  accommodation: number;
  discount: number;
  cleaning_fee: number;
  addons: number;
  levy: number;
  vat: number;
  total: number;
  avg_nightly_all_in: number;
  deposit: number;
  due_now: number;
  deposit_available: boolean;
  balance_due_date: string;
  lines: QuoteLine[];
  /** On-request extras: shown, but only charged once Amina confirms (not in total / due_now). */
  pending?: QuoteLine[];
  approx: Record<string, number>;
  available?: boolean;
  problems?: string[];
}

export interface CalendarData {
  start: string;
  end: string;
  unavailable: string[];
  prices: Record<string, number>;
  min_nights: number;
  max_nights: number;
}

export interface Review {
  id: number;
  rating: number;
  comment: string;
  guest: string;
  country: string;
  date: string;
  host_response: string;
  categories: Record<string, number>;
}

export interface PaymentResult {
  payment_id?: number;
  method?: "mpesa" | "card";
  status?: string;
  amount?: number;
  purpose?: string;
  checkout_url?: string | null;
  message?: string;
  simulated?: boolean;
  error?: string;
  failure_code?: string | null;
  suggest?: PaymentSuggest | null;
}

export interface TripAddon {
  id: number;
  code: string;
  name: string;
  icon: string;
  quantity: number;
  total: number;
  status: string;
  details: Record<string, string>;
  requires_approval: boolean;
}

export interface Trip {
  ref: string;
  status: string;
  status_label: string;
  channel: string;
  channel_label: string;
  created_at: string;
  hold_expires_at: string | null;
  unit: { id: number; name: string; slug: string; headline: string; area: string; photos: string[]; checkin_time: string; checkout_time: string };
  check_in: string;
  check_out: string;
  nights: number;
  adults: number;
  children: number;
  infants: number;
  guests: number;
  price: {
    lines: QuoteLine[];
    total: number;
    amount_paid: number;
    amount_refunded: number;
    refund_pending?: number;
    balance_due: number;
    amount_due_now: number;
    payment_status: string;
    payment_status_label: string;
    payment_plan: string;
    balance_due_date: string;
    balance_overdue?: boolean;
    pending?: QuoteLine[];
  };
  addons: TripAddon[];
  breakfast: (Record<string, string> & { people: number; summary: string }) | null;
  payments: TripPayment[];
  can_change?: boolean;
  changes?: ChangeRequest[];
  arrival: { eta: string; mode: string; vehicle_plate: string; special_requests: string };
  checkin: {
    time: string;
    checkout_time: string;
    method: string;
    reveal_at: string;
    details_visible: boolean;
    address?: string;
    map_link?: string;
    location?: { lat: number; lng: number } | null;
    directions?: string;
    landmark?: string;
    wifi_name?: string;
    wifi_password?: string;
    house_manual?: string;
    parking?: string;
    local_tips?: string;
    code?: string;
    code_valid_from?: string;
    code_valid_until?: string;
  };
  occupants: { id: number; full_name: string; id_type: string; id_last4: string; nationality: string; is_minor: boolean; is_lead: boolean }[];
  id_registered: boolean;
  require_id: boolean;
  cancellation: { policy: string; text: string; refund?: number; percent?: number; paid?: number; policy_text?: string };
  review: { rating: number; comment: string; host_response: string } | null;
  can_cancel: boolean;
  can_checkout: boolean;
  can_review: boolean;
  can_add_extras: boolean;
  can_pay: boolean;
  timeline: { kind: string; text: string; created_at: string; channel: string }[];
  tra_licence: string;
  support: { sms: string; voice: string; ussd: string };
  // host-only
  guest?: {
    id: number; name: string; phone: string; email: string; nationality: string; lang: string; tags: string[]; notes: string; blocked: boolean;
    id_type: string; id_last4: string; id_verified: boolean; stays: number;
  };
  risk?: { score: number; flags: { code: string; label: string }[] };
  host_notes?: string;
  sim_swap_status?: string;
  purpose?: string;
  codes?: { code: string; provider: string; valid_from: string; valid_until: string; sent_at: string | null; revoked_at: string | null; revoke_reason: string }[];
  refunds?: { id: number; amount: number; method: string; status: string; created_at: string; reference: string }[];
  cancel_info?: { cancelled_at: string | null; by: string; reason: string };
}

export type PaymentSuggest = "retry" | "card" | "deposit" | "wait" | "paybill";

export interface TripPayment {
  id: number;
  method: string;
  method_label: string;
  amount: number;
  status: string;
  purpose: string;
  created_at: string;
  reference: string;
  failure_code?: string | null;
  failure_message?: string | null;
  retryable?: boolean;
  suggest?: PaymentSuggest | null;
}

export interface StayShape {
  check_in: string;
  check_out: string;
  adults: number;
  children: number;
}

export interface ChangeRequest {
  id: number;
  status: "pending_host" | "pending_payment" | "applied" | "declined" | "expired" | "cancelled";
  status_label: string;
  old: StayShape;
  new: StayShape;
  delta: number;
  refund_amount: number;
  pay_now: number;
  requested_by: "guest" | "host";
  created_at: string;
  expires_at: string | null;
}

export interface ChangeQuote {
  available: boolean;
  reason: string | null;
  nights: number;
  old_total: number;
  new_total: number;
  delta: number;
  pay_now: number;
  refund: number;
  policy_text: string;
  instant: boolean;
  lines: QuoteLine[];
}

export interface WaitlistEntry {
  id: number;
  status: "waiting" | "offered" | "booked" | "expired";
  unit: { slug: string; name: string; area: string; photo: string } | null;
  area: { slug: string; name: string } | null;
  check_in: string;
  check_out: string;
  nights: number;
  guests: number;
  created_at: string;
  offered_at: string | null;
  book_url: string | null;
}

export interface Invoice {
  number: string;
  issued_at: string;
  seller: { name: string; kra_pin: string; address: string; tra_licence: string; vat_registered: boolean };
  buyer: { name: string; phone: string; kra_pin: string };
  lines: { label: string; qty: number; unit_price: number; amount: number }[];
  subtotal: number;
  vat: number;
  levy: number;
  total: number;
  paid: number;
  balance: number;
  payments: { date: string; method: string; reference: string; amount: number }[];
  credit_notes: { number: string; date: string; amount: number; reason: string }[];
  etims: { status: string; invoice_no: string | null };
}

export interface TripCard {
  ref: string;
  status: string;
  status_label: string;
  check_in: string;
  check_out: string;
  nights: number;
  total: number;
  balance_due: number;
  payment_status: string;
  channel: string;
  unit: { name: string; slug: string; area: string; cover: string };
  hold_expires_at: string | null;
}

export interface ChatMessage {
  id: number;
  direction: "in" | "out";
  channel: string;
  sender: string;
  body: string;
  kind: string;
  handled: string;
  status: string;
  created_at: string;
  delivered_at: string | null;
  booking: string | null;
  sent_by: string | null;
  failure_reason: string;
}

export interface FaqItem {
  id: number;
  category: string;
  question: string;
  answer: string;
}

// ---------- Africa's Talking challenge add-ons: local guide, service alerts, support desk, rewards ----------

export interface GuidePlace {
  id: number;
  slug: string;
  name: string;
  category: string;
  category_label: string;
  area: { slug: string; name: string } | null;
  summary: string;
  description: string;
  tips: string;
  hours: string;
  price: string;
  phone: string;
  website: string;
  latitude: number | null;
  longitude: number | null;
  photo: string;
  featured: boolean;
  map_url: string;
  distance_km?: number | null;
}

export interface GuideEvent {
  id: number;
  title: string;
  summary: string;
  date: string;
  time: string;
  price: string;
  addon_code: string;
  link: string;
  place: { slug: string; name: string } | null;
  area: string | null;
  weekly: boolean;
}

export interface GuideData {
  categories: { key: string; label: string; count: number }[];
  areas: { slug: string; name: string }[];
  places: GuidePlace[];
  events: GuideEvent[];
}

export interface ServiceNotice {
  id: number;
  kind: "outage" | "maintenance" | "advisory";
  kind_label: string;
  service: string;
  service_label: string;
  status: "scheduled" | "active";
  title: string;
  message: string;
  starts_at: string;
  expected_end: string | null;
}

export interface SupportTicket {
  id: number;
  ref: string;
  category: string;
  category_label: string;
  status: "open" | "in_progress" | "resolved" | "closed";
  status_label: string;
  subject: string;
  description: string;
  booking: string | null;
  created_at: string;
  updated_at: string;
  resolution: string;
  rating: number | null;
  can_rate: boolean;
  events: { kind: string; text: string; created_at: string }[];
}

export interface Rewards {
  enabled: boolean;
  points: number;
  code: string;
  share_text: string;
  referred_by: string | null;
  referral_status: "pending" | "rewarded" | "void" | null;
  can_enter_code: boolean;
  kenyan: boolean;
  redeem: { points: number; airtime: number; data_mb: number; can_airtime: boolean; can_data: boolean; why_not: string };
  rules: { points_per_100: number; review_points: number; referral_airtime: number; referee_airtime: number };
  history: { kind: "points" | "payout"; text: string; points: number | null; amount_text: string | null; status: string | null; created_at: string }[];
  message?: string;
}
