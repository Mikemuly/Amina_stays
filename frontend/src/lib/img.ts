// Responsive sources for remote listing photos (Unsplash supports on-the-fly width).
export function sized(src: string, w: number) {
  if (!src) return src;
  if (src.includes("images.unsplash.com")) {
    const u = new URL(src);
    u.searchParams.set("w", String(w));
    u.searchParams.set("q", w > 1200 ? "80" : "72");
    u.searchParams.set("auto", "format");
    u.searchParams.set("fit", "crop");
    return u.toString();
  }
  return src;
}

export function srcSet(src: string, widths = [480, 720, 960, 1280]) {
  if (!src?.includes("images.unsplash.com")) return undefined;
  return widths.map((w) => `${sized(src, w)} ${w}w`).join(", ");
}
