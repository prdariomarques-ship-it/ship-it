"use client";

import { AdminPageHeader } from "@/components/admin/PageHeader";
import { EmptyState } from "@/components/admin/EmptyState";
import { Input } from "@/components/admin/ui/input";
import { Search } from "lucide-react";

export default function RuntimeAuditPage() {
  return (
    <div>
      <AdminPageHeader
        title="Audit Trail"
        subtitle="Chronological view of state transitions, recovery events, and errors"
      />

      <div className="mb-6 flex gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Search events..." className="pl-10" />
        </div>
        <select className="rounded-md border border-input bg-background px-3 py-2 text-sm">
          <option>All Events</option>
          <option>State Transitions</option>
          <option>Recovery Events</option>
          <option>Errors</option>
        </select>
      </div>

      <EmptyState title="No audit events yet" />
    </div>
  );
}
