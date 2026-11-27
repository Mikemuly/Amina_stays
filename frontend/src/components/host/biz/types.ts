// Response shapes for the Grow + Run-the-business console pages (mirrors backend views/serializers).

// ---------- listings ----------

export type ListingStatus = "active" | "paused" | "draft";
export type Housekeeping = "clean" | "dirty" | "cleaning" | "inspect";
export type CancellationPolicy = "flexible" | "moderate" | "firm" | "strict";
export type AccessMethod = "simulated" | "igloohome" | "ttlock" | "nuki" | "lockbox" | "caretaker";

export interface HostPhoto {
  id: number;
  url: string;
  image: string | null;
  src: string;
  caption: string;
  room: string;
  sort_order: number;
}

export interface Sleeping {
  room: string;
  beds: string;
}

export interface Highlight {
  icon: string;
  title: string;
  text: string;
}

export interface HostListing {
  id: number;
  slug: string;
  area: string;
  amenity_codes: string[];
  photos: HostPhoto[];
  ical_export_url: string;
  name: string;
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
  base_price: number;
  weekend_price: number | null;
  cleaning_fee: number;
  weekly_discount: number;
  monthly_discount: number;
  min_nights: number;
  max_nights: number;
  checkin_time: string;
  checkout_time: string;
  cancellation_policy: CancellationPolicy;
  latitude: string | null;
  longitude: string | null;
  address: string;
  directions: string;
  landmark: string;
  map_link: string;
  wifi_name: string;
  wifi_password: string;
  access_method: AccessMethod;
  lock_device_id: string;
  parking: string;
  house_rules: string[];
  pets_allowed: boolean;
  smoking_allowed: boolean;
  events_allowed: boolean;
  quiet_hours: string;
  safety_features: string[];
  house_manual: string;
  local_tips: string;
  highlights: Highlight[];
  tags: string[];
  breakfast_available: boolean;
  status: ListingStatus;
  tra_licence_number: string;
  housekeeping: Housekeeping;
  is_featured: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface Amenity {
  id: number;
  code: string;
  name: string;
  icon: string;
  category: string;
  description: string;
}

export interface ICalFeed {
  id: number;
  unit: number;
  unit_name: string;
  name: string;
  url: string;
  active: boolean;
  last_synced_at: string | null;
  last_ok: boolean;
  last_error: string;
  events_count: number;
}

// ---------- guests ----------

export interface GuestRow {
  id: number;
  phone: string;
  name: string;
  email: string;
  lang: string;
  nationality: string;
  tags: string[];
  blocked: boolean;
  first_channel: string;
  marketing_opt_in: boolean;
  opted_out: boolean;
  id_registered: boolean;
  stays: number | null;
  spend: number;
  last_stay: string | null;
  joined: string;
}

export interface GuestBooking {
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

export interface GuestDetail extends GuestRow {
  notes: string;
  block_reason: string;
  identity: { type: string; last4: string; verified: boolean };
  bookings: GuestBooking[];
  thread_id: number | null;
  reviews: { ref: string; rating: number; comment: string }[];
}

// ---------- messaging ----------

export interface Automation {
  id: number;
  key: string;
  name: string;
  description: string;
  anchor: "confirmed" | "check_in" | "check_out";
  offset_days: number;
  send_time: string;
  template_key: string;
  channel: string;
  enabled: boolean;
  sort_order: number;
}

export interface AutomationPreview {
  text: string;
  ref?: string;
  segments?: number;
}

export type TemplateLang = "en" | "sw" | "it" | "de" | "fr";

export interface TemplateItem {
  key: string;
  description: string;
  langs: Record<TemplateLang, { body: string; default: string; custom: boolean }>;
}

export interface TemplatesResponse {
  templates: TemplateItem[];
  placeholders: string[];
}

export interface Faq {
  id: number;
  category: string;
  question: string;
  answer_en: string;
  answer_sw: string;
  answer_fr: string;
  answer_de: string;
  keywords: string;
  unit: number | null;
  active: boolean;
  hits: number;
  sort_order: number;
}

export interface FaqTestResult {
  matched: boolean;
  question: string | null;
  answer: string | null;
}

export type Audience = "in_house" | "arriving" | "upcoming" | "past" | "waitlist" | "staff";

export interface BroadcastRow {
  id: number;
  audience: Audience;
  audience_label: string;
  body: string;
  recipients: number;
  is_marketing: boolean;
  created_at: string;
  unit: string | null;
}

// ---------- reviews ----------

export interface ReviewStats {
  rating: number | null;
  count: number;
  categories: Record<string, number>;
  guest_favourite: boolean;
}

export interface HostReview {
  id: number;
  ref: string;
  unit: string;
  guest: string;
  nationality: string;
  rating: number;
  comment: string;
  categories: Record<string, number>;
  host_response: string;
  channel: string;
  created_at: string;
}

export interface HostReviewsResponse {
  summary: ReviewStats;
  by_unit: (ReviewStats & { unit: string })[];
  reviews: HostReview[];
}

// ---------- insights ----------

export interface Kpis {
  period: { start: string; end: string };
  occupancy: number;
  booked_nights: number;
  available_nights: number;
  room_revenue: number;
  adr: number;
  revpar: number;
  collected: number;
  refunded: number;
  by_method: Record<string, number>;
  bookings: number;
  by_channel: Record<string, { bookings: number; revenue: number }>;
  lead_time_days: number;
  avg_stay_nights: number;
  cancellation_rate: number;
  direct_share: number;
  addon_revenue: number;
  levy_due: number;
  response_minutes: number | null;
  auto_answer_rate: number;
  messages_in: number;
  reviews: number;
  rating: number | null;
}

export interface SeriesPoint {
  date: string;
  occupancy: number;
  revenue: number;
  bookings: Record<string, number>;
}

export interface ForwardWeek {
  week_start: string;
  occupancy: number;
  booked_nights: number;
  available_nights: number;
}

export interface InsightsResponse {
  kpis: Kpis;
  previous: Kpis;
  series: SeriesPoint[];
  forward: ForwardWeek[];
  days: number;
}

// ---------- payments ----------

export interface PaymentRow {
  id: number;
  ref: string;
  guest: string;
  unit: string;
  amount: number;
  method: string;
  method_label: string;
  purpose: string;
  status: string;
  provider: string;
  reference: string;
  failure_reason: string;
  created_at: string;
  completed_at: string | null;
}

export interface RefundRow {
  id: number;
  ref: string;
  guest: string;
  phone: string;
  amount: number;
  method: string;
  status: string;
  reason: string;
  reference: string;
  created_at: string;
}

export interface OutstandingRow {
  ref: string;
  guest: string;
  phone: string;
  unit: string;
  check_in: string;
  balance_due: number;
  due_on: string | null;
  overdue: boolean;
}

export interface UnmatchedRow {
  id: number;
  trans_id: string;
  amount: number;
  phone: string;
  bill_ref: string;
  received_at: string;
}

export interface LedgerResponse {
  payments: PaymentRow[];
  refunds: RefundRow[];
  outstanding?: OutstandingRow[];
  unmatched?: UnmatchedRow[];
}

// ---------- safety & compliance ----------

export interface AlertItem {
  id: number;
  kind: string;
  kind_label: string;
  severity: "critical" | "high" | "medium" | "low";
  status: "open" | "acknowledged" | "resolved";
  source: string;
  phone: string;
  summary: string;
  details: string;
  call_status: string;
  calls_made: number;
  booking: string | null;
  created_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  resolution_note: string;
  resolved_by: string | null;
}

export interface RegisterRow {
  ref: string;
  unit: string;
  address: string;
  name: string;
  lead_guest: boolean;
  minor: boolean;
  id_type: string;
  id_last4: string;
  nationality: string;
  phone: string;
  check_in: string;
  check_out: string;
  arrived_at: string | null;
  left_at: string | null;
  vehicle: string;
}

export interface RegisterResponse {
  from: string;
  to: string;
  rows: RegisterRow[];
  missing_id: number;
}

export interface TraReturn {
  month: string;
  units: number;
  occupancy: number;
  room_nights_sold: number;
  room_nights_available: number;
  guest_nights: number;
  arrivals: number;
  visitors_by_country: Record<string, number>;
  room_revenue: number;
  tourism_levy: number;
}

// ---------- settings ----------

export interface HostSettings {
  business_name: string;
  host_name: string;
  host_phone: string;
  backup_phone: string;
  support_email: string;
  tagline: string;
  default_checkin_time: string;
  default_checkout_time: string;
  code_release_time: string;
  hold_minutes: number;
  deposit_percent: number;
  balance_due_days: number;
  tourism_levy_percent: string;
  vat_percent: string;
  vat_registered: boolean;
  tra_licence_number: string;
  tra_licence_expiry: string | null;
  instant_changes?: boolean;
  odpc_registration: string;
  kra_pin: string;
  require_id_before_code: boolean;
  id_retention_days: number;
  sim_swap_check: boolean;
  promo_window_start: number;
  promo_window_end: number;
  welcome_data_mb: number;
  voice_welcome_call: boolean;
  goodwill_airtime_kes: number;
  review_delay_minutes: number;
  quiet_hours_start: number;
  quiet_hours_end: number;
  auto_answer: boolean;
  usd_rate: string;
  eur_rate: string;
  gbp_rate: string;
  updated_at: string;
}

export interface StaffMember {
  id: number;
  phone: string;
  name: string;
  role: string;
  lang: string;
  is_active: boolean;
  unit_ids: number[];
  open_tasks: number;
}

export interface RoleOption {
  value: string;
  label: string;
}

export interface HostAddon {
  id: number;
  unit_ids: number[];
  code: string;
  name: string;
  short: string;
  description: string;
  category: string;
  icon: string;
  price: number;
  pricing: string;
  requires_approval: boolean;
  options: Record<string, unknown>;
  lead_hours: number;
  active: boolean;
  sort_order: number;
}

export type RuleKind = "season" | "weekday" | "last_minute" | "early_bird";
export type AdjustType = "percent" | "amount" | "fixed";

export interface PriceRule {
  id: number;
  unit: number | null;
  unit_name: string;
  name: string;
  kind: RuleKind;
  start_date: string | null;
  end_date: string | null;
  weekdays: number[];
  days_before: number | null;
  adjust_type: AdjustType;
  value: string;
  priority: number;
  active: boolean;
}

// ---------- Africa's Talking ----------

export interface AtProduct {
  key: string;
  name: string;
  ready: boolean;
  detail: string;
  callbacks: Record<string, string>;
}

export interface ChannelsResponse {
  username: string;
  sandbox: boolean;
  configured: boolean;
  balance: string | null;
  webhook_secret: boolean;
  products: AtProduct[];
  last_seen: Record<string, string | null>;
  jobs: { key: string; last_run_at: string | null; ok: boolean; runs: number }[];
}

// ---------- support desk ----------

export type TicketCategory = "complaint" | "issue" | "callback" | "billing" | "booking" | "feedback" | "other";
export type TicketStatus = "open" | "in_progress" | "resolved" | "closed";
export type TicketPriority = "low" | "normal" | "high" | "urgent";

export interface TicketRow {
  id: number;
  ref: string;
  category: TicketCategory;
  category_label: string;
  status: TicketStatus;
  status_label: string;
  priority: TicketPriority;
  channel: "sms" | "ussd" | "voice" | "web" | "host";
  subject: string;
  description: string;
  phone: string;
  guest: { name: string; phone: string } | null;
  booking: string | null;
  unit: string | null;
  task: { id: number; status: string; assignee: string | null } | null;
  recording_url: string;
  created_at: string;
  first_response_due: string | null;
  first_response_at: string | null;
  overdue: boolean;
  resolved_at: string | null;
  resolution: string;
  rating: number | null;
  rating_comment: string;
  escalation_level: number;
  last_activity_at: string;
}

export interface TicketEvent {
  id: number;
  kind: "created" | "reply" | "guest" | "note" | "status" | "call" | "escalated" | "rating" | "task";
  text: string;
  channel: string;
  actor: string | null;
  created_at: string;
}

export interface TicketDetail extends TicketRow {
  events: TicketEvent[];
}

export interface SupportCounts {
  open: number;
  overdue: number;
  resolved_7d: number;
  avg_first_response_min: number | null;
  csat: number | null;
  csat_count: number;
}

export interface TicketsResponse {
  counts: SupportCounts;
  tickets: TicketRow[];
}

export interface TicketCallResult {
  placed: boolean;
  dry_run: boolean;
  detail: string;
  ticket: TicketDetail;
}

// ---------- service alerts ----------

export type NoticeKind = "outage" | "maintenance" | "advisory";
export type NoticeStatus = "scheduled" | "active" | "resolved" | "cancelled";

export interface NoticeRow {
  id: number;
  kind: NoticeKind;
  kind_label: string;
  service: string;
  service_label: string;
  status: NoticeStatus;
  status_label: string;
  title: string;
  message: string;
  units: { id: number; name: string }[];
  all_homes: boolean;
  starts_at: string;
  expected_end: string | null;
  resolved_at: string | null;
  resolution: string;
  data_mb: number;
  notified: number;
  source: string;
  created_by: string | null;
  created_at: string;
}

export interface NoticesResponse {
  notices: NoticeRow[];
  services: [string, string][];
  kinds: [NoticeKind, string][];
  default_data_mb: number;
  data_services: string[];
}

export interface NoticePreview {
  guests: number;
  sms: string;
  segments: number;
}

// ---------- local guide ----------

export type PlaceCategory = "sights" | "beaches" | "nature" | "food" | "markets" | "culture" | "evenings" | "transport" | "essentials";

export interface HostPlace {
  id: number;
  name: string;
  slug: string;
  category: PlaceCategory;
  category_label: string;
  area: string | null;
  summary: string;
  summary_sw: string;
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
  active: boolean;
  sort_order: number;
  hits: number;
  map_url: string;
  updated_at: string;
}

export interface HostGuideEvent {
  id: number;
  title: string;
  summary: string;
  place: number | null;
  area: string | null;
  weekday: number | null;
  starts_on: string | null;
  ends_on: string | null;
  yearly: boolean;
  time: string;
  price: string;
  addon_code: string;
  link: string;
  active: boolean;
  next_on: string | null;
}

// ---------- rewards & airtime ----------

export interface RewardsProgram {
  enabled: boolean;
  points_per_100: number;
  review_points: number;
  referral_airtime: number;
  referee_airtime: number;
  redeem_points: number;
  redeem_airtime: number;
  redeem_data_mb: number;
  outage_data_mb: number;
  monthly_airtime_budget: number;
}

export interface RewardsStats {
  members: number;
  points_outstanding: number;
  airtime_month: number;
  airtime_budget: number;
  data_month_mb: number;
  referrals_completed: number;
  referrals_pending: number;
  payouts_held: number;
  guests: number;
}

export type PayoutStatus = "held" | "queued" | "sent" | "success" | "failed" | "rejected" | "simulated";

export interface PayoutRow {
  id: number;
  kind: "airtime" | "data";
  kind_label: string;
  amount: number;
  amount_text: string;
  reason: "referral" | "referee" | "redeem" | "outage" | "manual";
  reason_label: string;
  phone: string;
  guest: string | null;
  booking: string | null;
  note: string;
  status: PayoutStatus;
  status_label: string;
  error: string;
  created_at: string;
  completed_at: string | null;
}

export interface ReferralRow {
  referrer: string;
  referee: string;
  code: string | null;
  status: "pending" | "rewarded" | "void";
  status_label: string;
  booking: string | null;
  created_at: string | null;
}

export interface RewardsResponse {
  program: RewardsProgram;
  stats: RewardsStats;
  payouts: PayoutRow[];
  referrals: ReferralRow[];
}
