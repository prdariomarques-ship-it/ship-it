import { redirect } from "next/navigation";

// This page and /admin/logs served the exact same admin-only LogEntry data
// (both endpoints require the same admin role, no user-scoping) with very
// different capability: this one had no filter and no pagination beyond a
// fixed limit=50, so it showed nothing but back-to-back job:observation.tick
// noise. Rather than duplicate /admin/logs's filter+search UI a second time,
// redirect here — anyone with this URL bookmarked still lands somewhere
// useful instead of the inferior duplicate.
export default function LogsPage() {
  redirect("/admin/logs");
}
