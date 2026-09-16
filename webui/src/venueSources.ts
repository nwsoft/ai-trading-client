import { VENUE_REGISTRY } from "./generatedVenueRegistry";

// Generated from trading/exchanges/venue_capabilities.py. Runtime, Settings,
// Strategy Studio, and daltrading therefore consume the same venue inventory.
export const CRYPTO_SOURCES: string[] = VENUE_REGISTRY.venues
  .filter((item) => item.service === "blockchain")
  .map((item) => item.client_id);
export const STOCK_SOURCES: string[] = VENUE_REGISTRY.venues
  .filter((item) => item.service === "stock")
  .map((item) => item.client_id);

export function venueProfile(value: string) {
  const normalized = String(value || "").trim().toLowerCase();
  return VENUE_REGISTRY.venues.find((item) =>
    item.client_id.toLowerCase() === normalized
    || item.id.toLowerCase() === normalized
    || item.aliases.some((alias) => alias.toLowerCase() === normalized),
  );
}

export function venueProfilesForService(service: string) {
  return VENUE_REGISTRY.venues.filter((item) => item.service === service);
}

export function sourcesForService(service: string): string[] {
  return service === "stock" ? STOCK_SOURCES : CRYPTO_SOURCES;
}
