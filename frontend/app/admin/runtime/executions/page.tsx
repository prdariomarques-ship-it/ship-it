"use client";

import { useState } from "react";
import { AdminPageHeader } from "@/components/admin/PageHeader";
import { EmptyState } from "@/components/admin/EmptyState";
import { Search, Filter } from "lucide-react";
import { Input } from "@/components/admin/ui/input";

export default function RuntimeExecutionsPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");

  return (
    <div>
      <AdminPageHeader
        title="Executions"
        subtitle="Monitor all workflow executions, including running, completed, recovered, and failed"
      />

      <div className="mb-6 flex flex-col gap-4 md:flex-row">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search execution ID or correlation ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-md border border-input bg-background px-3 py-2 text-sm"
        >
          <option value="all">All Status</option>
          <option value="running">Running</option>
          <option value="completed">Completed</option>
          <option value="recovered">Recovered</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      <EmptyState title="No executions yet" />
    </div>
  );
}
