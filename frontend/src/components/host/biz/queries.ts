"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { get } from "@/lib/api";
import type { Area } from "@/lib/types";

import type { Amenity, HostListing, HostSettings } from "./types";

export function useListings() {
  return useQuery({ queryKey: ["host", "listings"], queryFn: () => get<HostListing[]>("/api/host/listings") });
}

export function useHostSettings() {
  return useQuery({ queryKey: ["host", "settings"], queryFn: () => get<HostSettings>("/api/host/settings") });
}

export function useAreas() {
  return useQuery({ queryKey: ["host", "areas"], queryFn: () => get<Area[]>("/api/areas"), staleTime: 5 * 60_000 });
}

export function useAmenities() {
  return useQuery({ queryKey: ["host", "amenities"], queryFn: () => get<Amenity[]>("/api/amenities"), staleTime: 5 * 60_000 });
}

/** After any console mutation: refresh everything under ["host"] (sidebar badges included). */
export function useInvalidateHost() {
  const qc = useQueryClient();
  return React.useCallback(() => qc.invalidateQueries({ queryKey: ["host"] }), [qc]);
}
