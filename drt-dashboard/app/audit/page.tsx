"use client";

import { AlertCircle } from "lucide-react";

export default function AuditPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white mb-2">Audit Trail</h1>
        <p className="text-drt-400">
          Chronological view of all state transitions, recovery events, and errors.
        </p>
      </div>

      <div className="bg-drt-900 border border-drt-800 rounded-lg p-4 space-y-3">
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Search events..."
            className="flex-1 bg-drt-800 border border-drt-700 rounded px-4 py-2 text-white placeholder-drt-500 focus:outline-none focus:border-blue-500"
          />
          <select className="bg-drt-800 border border-drt-700 rounded px-4 py-2 text-white focus:outline-none focus:border-blue-500">
            <option>All Events</option>
            <option>State Transitions</option>
            <option>Recovery Events</option>
            <option>Errors</option>
          </select>
        </div>
      </div>

      <div className="bg-drt-900 border border-drt-800 rounded-lg p-8 text-center">
        <AlertCircle className="w-12 h-12 text-drt-600 mx-auto mb-4" />
        <p className="text-drt-400">No audit events yet</p>
        <p className="text-sm text-drt-500">
          Execute workflows to generate audit events.
        </p>
      </div>
    </div>
  );
}
