/**
 * RouteCare AI - external turn-by-turn navigation (Phase 11).
 *
 * Deliberately NOT a routing/maps provider of our own - `app/services/routing.py`'s
 * RoutingProvider abstraction computes driving time/distance for RouteCare's own optimization and
 * travel-time features; this is a different job entirely (per the task's explicit "do not build a
 * full replacement for Google Maps/Waze navigation"). `buildNavigationUrl` just constructs the
 * one URL every navigation entry point in the app hands to `window.open`, so swapping the
 * destination service (e.g. preferring Apple Maps on iOS, or a self-hosted alternative later) is a
 * one-function change - the same "provider abstraction" principle as the backend's, applied to a
 * link instead of an API call.
 *
 * Google Maps' `/maps/dir/?api=1` universal link is used because it degrades gracefully
 * everywhere without any app-detection logic of our own: on a phone with the Google Maps app
 * installed it opens directly into turn-by-turn navigation; without the app (or on desktop) it
 * opens Google Maps in the browser with the route already drawn. No other patient information
 * (name, phone, notes) is ever included in the URL - only the destination location itself, per
 * the task's explicit "do not expose patient information unnecessarily to external services."
 */

export interface NavigationDestination {
  latitude: number | null;
  longitude: number | null;
  /** Street address to fall back to when coordinates aren't available yet (not geocoded). */
  address: string;
}

/** Returns a URL that opens turn-by-turn directions to `destination`, or null if there's truly
 * nowhere to send the user (no coordinates AND no address text). */
export function buildNavigationUrl(destination: NavigationDestination): string | null {
  if (destination.latitude != null && destination.longitude != null) {
    return `https://www.google.com/maps/dir/?api=1&destination=${destination.latitude},${destination.longitude}`;
  }
  if (destination.address.trim()) {
    return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(destination.address.trim())}`;
  }
  return null;
}
