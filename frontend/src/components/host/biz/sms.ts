// GSM-7 / UCS-2 SMS maths, mirroring backend/apps/messaging/services.py (to_gsm, sms_segments).

const GSM_BASIC = new Set(
  Array.from("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ ÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"),
);
const GSM_EXT = new Set(Array.from("^{}\\[~]|€"));
const REPLACE: Record<string, string> = {
  "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "…": "...", "•": "-", "→": "->", "★": "*", "\u00a0": " ",
};

const isGsm = (c: string) => GSM_BASIC.has(c) || GSM_EXT.has(c);

export interface SmsInfo {
  encoding: "GSM-7" | "Unicode";
  length: number;
  segments: number;
  /** characters available in the current number of segments */
  limit: number;
  /** characters that force Unicode (70 / 67 per part) */
  offenders: string[];
}

export function smsInfo(text: string): SmsInfo {
  const chars = Array.from(text);
  const offenders = [...new Set(chars.filter((c) => !isGsm(c)))];
  const gsm = offenders.length === 0;
  // GSM-7 extension characters take two septets; UCS-2 counts UTF-16 code units (emoji = 2)
  const length = gsm ? chars.reduce((n, c) => n + (GSM_EXT.has(c) ? 2 : 1), 0) : text.length;
  const single = gsm ? 160 : 70;
  const multi = gsm ? 153 : 67;
  const segments = length === 0 ? 0 : length <= single ? 1 : Math.ceil(length / multi);
  return { encoding: gsm ? "GSM-7" : "Unicode", length, segments, limit: segments <= 1 ? single : segments * multi, offenders };
}

/** Plain-text equivalent that stays inside GSM-7 (smart quotes → ', em dash → -, accents stripped, emoji dropped). */
export function toGsm(text: string) {
  return Array.from(text)
    .map((ch) => {
      const r = REPLACE[ch] ?? ch;
      if (Array.from(r).every(isGsm)) return r;
      return r.normalize("NFKD").replace(/[^\x00-\x7F]/g, "");
    })
    .join("");
}

export function describeChar(c: string) {
  if (c === "\u00a0") return "non-breaking space";
  if (c === "\t") return "tab";
  return c;
}

/** Python str.format-style rendering with sample values; unknown placeholders render empty (like the backend). */
export function renderPlaceholders(body: string, values: Record<string, string | number>) {
  return body
    .replace(/\{(\w+)\}/g, (_, k: string) => (values[k] !== undefined ? String(values[k]) : ""))
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

export const SAMPLE_VALUES: Record<string, string | number> = {
  first_name: "Wanjiku",
  name: "Wanjiku Kamau",
  unit: "Nyali Breeze Studio",
  area: "Nyali",
  ref: "AMS-4821",
  dates: "12-15 Dec",
  check_in: "Fri 12 Dec",
  check_out: "Mon 15 Dec",
  nights: 3,
  s: "s",
  total: "KES 18,450",
  paid: "KES 18,450",
  amount: "KES 18,450",
  balance: "KES 12,915",
  balance_note: "",
  due_date: "Thu 11 Dec",
  checkin_time: "2pm",
  checkout_time: "11am",
  wifi: "NyaliBreeze_5G / karibu-nyali-24",
  directions: "From Links Road turn at the Shell station towards City Mall, second left after the back gate.",
  landmark: "Behind City Mall, blue gate opposite the pharmacy",
  map_link: "maps.google.com/?q=-4.03,39.719",
  trip_link: "aminastays.co.ke/t/AMS-4821",
  link: "aminastays.co.ke/stays/nyali-breeze-studio",
  business: "Amina Stays",
  host: "Amina",
  tips: "Java House Nyali for breakfast; Uber/Bolt work well; avoid the beach after dark.",
  taxi: "Bolt or Uber, or call Juma 0712 345 678",
  code: "482193",
  valid_from: "Fri 12 Dec, 2pm",
  valid_until: "Mon 15 Dec, 11am",
  minutes: 10,
  reason: "insufficient funds",
  clean_price: "KES 1,500",
  prices: "Nyali Breeze Studio (Nyali, 1BR, 2 guests) KES 4,500; Blue Reef Apartment (Nyali, 2BR, 4 guests) KES 8,500",
  ussd_code: "*384*4821#",
  sms_number: "21525",
  website: "aminastays.co.ke",
  deposit_percent: 30,
};
