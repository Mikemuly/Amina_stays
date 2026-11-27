"use client";

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import Link from "next/link";
import * as React from "react";
import { Circle, MapContainer, Marker, Popup, TileLayer, ZoomControl, useMap } from "react-leaflet";

import { StarIcon, cardTitle } from "@/components/site/listing-card";
import { useMoney } from "@/components/site/locale";
import { sized } from "@/lib/img";
import type { ListingCard } from "@/lib/types";

// OpenStreetMap tiles, softened in CSS (.leaflet-tile-pane) toward the calm basemaps of the big booking sites.
const TILES = process.env.NEXT_PUBLIC_TILE_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

const pinIcon = (label: string, active: boolean) =>
  L.divIcon({ className: "", iconSize: [0, 0], html: `<div class="amina-pin${active ? " is-active" : ""}">${label}</div>` });

/** Fits the map to the homes once its container has settled (and again when the set or size changes). */
function Fit({ points, token }: { points: [number, number][]; token?: unknown }) {
  const map = useMap();
  const key = points.map((p) => p.join(",")).join("|");
  React.useEffect(() => {
    const t = setTimeout(() => {
      map.invalidateSize();
      if (points.length) map.fitBounds(L.latLngBounds(points), { padding: [64, 64], maxZoom: 13 });
    }, 200);
    return () => clearTimeout(t);
    // refit only when the set of homes or the container changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, key, token]);
  return null;
}

export default function ListingsMap({ listings, query, hoverId, resizeToken }: { listings: ListingCard[]; query: string; hoverId?: number | null; resizeToken?: unknown }) {
  const [selected, setSelected] = React.useState<number | null>(null);
  const money = useMoney();
  const points = React.useMemo(() => listings.filter((l) => l.location).map((l) => [l.location!.lat, l.location!.lng] as [number, number]), [listings]);
  return (
    <MapContainer center={[-4.05, 39.68]} zoom={11} scrollWheelZoom className="size-full" zoomControl={false} attributionControl>
      <TileLayer attribution={ATTRIBUTION} url={TILES} />
      <ZoomControl position="topright" />
      <Fit points={points} token={resizeToken} />
      {listings.map((l) =>
        l.location ? (
          <Marker
            key={l.id}
            position={[l.location.lat, l.location.lng]}
            icon={pinIcon(money(l.price.total ?? l.price.from_nightly), hoverId === l.id || selected === l.id)}
            zIndexOffset={hoverId === l.id || selected === l.id ? 1000 : 0}
            eventHandlers={{ popupopen: () => setSelected(l.id), popupclose: () => setSelected(null) }}
          >
            <Popup closeButton={false} offset={[0, -14]} className="amina-popup" autoPanPadding={[24, 24]}>
              <Link href={`/stays/${l.slug}${query}`} className="block !text-ink no-underline">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={sized(l.photos[0], 640)} alt="" className="aspect-[3/2] w-full object-cover" />
                <span className="block px-4 pt-3 pb-4 font-sans">
                  <span className="flex items-center justify-between gap-2 text-[15px]">
                    <span className="truncate font-medium">{cardTitle(l)}</span>
                    {l.rating ? (
                      <span className="flex shrink-0 items-center gap-1">
                        <StarIcon /> {l.rating.toFixed(2)}
                      </span>
                    ) : null}
                  </span>
                  <span className="block truncate text-[15px] text-ink-2">{l.name}</span>
                  <span className="mt-1 block text-[15px]">
                    <b className="font-semibold">{money(l.price.total ?? l.price.from_nightly)}</b>
                    <span className="text-ink-2">{l.price.total ? ` for ${l.price.nights} nights` : " a night"}</span>
                  </span>
                </span>
              </Link>
            </Popup>
          </Marker>
        ) : null,
      )}
    </MapContainer>
  );
}

const HOME_PIN = L.divIcon({
  className: "",
  iconSize: [0, 0],
  html: `<div class="amina-home-pin"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 9v11h14V9"/></svg></div>`,
});

export function LocationMap({ lat, lng, exact = false, height = 480 }: { lat: number; lng: number; exact?: boolean; height?: number }) {
  return (
    <div className="overflow-hidden rounded-card" style={{ height }}>
      <MapContainer center={[lat, lng]} zoom={exact ? 16 : 14} scrollWheelZoom={false} className="size-full" zoomControl={false}>
        <TileLayer attribution={ATTRIBUTION} url={TILES} />
        <ZoomControl position="topright" />
        {!exact && <Circle center={[lat, lng]} radius={420} pathOptions={{ stroke: false, fillColor: "#e8553e", fillOpacity: 0.18 }} />}
        <Marker position={[lat, lng]} icon={HOME_PIN} />
      </MapContainer>
    </div>
  );
}
