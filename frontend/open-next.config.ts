// RouteCare AI - Cloudflare Workers adapter config (Phase 12 free-tier deployment).
// No R2 incremental cache configured - that's an optional performance feature (persistent
// ISR/data-cache across requests) requiring its own R2 bucket, out of scope for this MVP
// deployment. Falls back to OpenNext's default in-memory-per-request behavior instead.
import { defineCloudflareConfig } from "@opennextjs/cloudflare/config";

export default defineCloudflareConfig();
