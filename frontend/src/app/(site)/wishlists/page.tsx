import type { Metadata } from "next";

import { WishlistsView } from "@/components/site/wishlists-view";

export const metadata: Metadata = { title: "Wishlist" };

export default function Page() {
  return <WishlistsView />;
}
