"use client";

import { useState } from "react";
import { AdminPageHeader } from "@/components/admin/PageHeader";
import { AlertCircle } from "lucide-react";

export default function RuntimeWorkflowsPage() {
  const [yaml, setYaml] = useState("");

  return (
    <div>
      <AdminPageHeader
        title="Workflow Management"
        subtitle="Upload YAML workflows, perform dry runs, and execute them"
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div>
          <label className="mb-2 block text-sm font-medium">Workflow YAML</label>
          <textarea
            value={yaml}
            onChange={(e) => setYaml(e.target.value)}
            placeholder={`name: example
workflow_version: "1.0"
owner: operator
timeout: 300
steps:
  - name: step-1
    type: system`}
            className="h-64 w-full rounded-md border border-input bg-background p-3 font-mono text-sm"
          />
        </div>

        <div>
          <label className="mb-2 block text-sm font-medium">Result</label>
          <pre className="h-64 w-full rounded-md border border-input bg-background p-3 font-mono text-xs overflow-auto">
            {"Result will appear here..."}
          </pre>
        </div>
      </div>

      <div className="mt-6 flex gap-2">
        <button className="rounded-md bg-yellow-600 hover:bg-yellow-700 text-white px-4 py-2 text-sm font-medium">
          Dry Run
        </button>
        <button className="rounded-md bg-green-600 hover:bg-green-700 text-white px-4 py-2 text-sm font-medium">
          Execute
        </button>
      </div>
    </div>
  );
}
