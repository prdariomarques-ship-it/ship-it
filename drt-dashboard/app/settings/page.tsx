"use client";

import { Settings as SettingsIcon } from "lucide-react";

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-white mb-2">Settings</h1>
        <p className="text-drt-400">
          Runtime configuration, environment information, and LTS policy.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-drt-900 border border-drt-800 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <SettingsIcon className="w-5 h-5" />
            Runtime Configuration
          </h2>
          <div className="space-y-4">
            <ConfigField label="Runtime Version" value="1.0.0-LTS" readonly />
            <ConfigField label="Build Date" value="2026-07-14" readonly />
            <ConfigField label="Production Certified" value="Yes" readonly />
            <ConfigField label="Storage Mode" value="File-based + WAL" readonly />
          </div>
        </div>

        <div className="bg-drt-900 border border-drt-800 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Long-Term Support</h2>
          <div className="space-y-3">
            <div>
              <p className="text-drt-400 text-sm">LTS Period</p>
              <p className="text-white font-semibold">2026-07-14 to 2028-01-14</p>
            </div>
            <div>
              <p className="text-drt-400 text-sm">Bug Fix SLA</p>
              <p className="text-white">Within 24 hours</p>
            </div>
            <div>
              <p className="text-drt-400 text-sm">Security Fix SLA</p>
              <p className="text-white">Within 48 hours</p>
            </div>
            <div>
              <p className="text-drt-400 text-sm">Architecture Changes</p>
              <p className="text-red-400">Not permitted</p>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-drt-900 border border-drt-800 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Environment</h2>
        <div className="space-y-2 text-sm">
          <EnvVar label="RUNTIME_API" value={process.env.NEXT_PUBLIC_RUNTIME_API || "http://localhost:5000"} />
          <EnvVar label="NODE_ENV" value={process.env.NODE_ENV || "development"} />
          <EnvVar label="DASHBOARD_VERSION" value="1.0.0" />
        </div>
      </div>

      <div className="bg-yellow-950 border border-yellow-700 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-yellow-200 mb-3">Production Checklist</h2>
        <ul className="space-y-2 text-sm text-yellow-100">
          <li className="flex items-center gap-2">
            <span className="text-green-400">✓</span> Runtime certified for production
          </li>
          <li className="flex items-center gap-2">
            <span className="text-green-400">✓</span> 18-month Long-Term Support active
          </li>
          <li className="flex items-center gap-2">
            <span className="text-green-400">✓</span> Durability guaranteed with fsync()
          </li>
          <li className="flex items-center gap-2">
            <span className="text-green-400">✓</span> Crash recovery fully tested
          </li>
          <li className="flex items-center gap-2">
            <span className="text-green-400">✓</span> No external dependencies
          </li>
        </ul>
      </div>
    </div>
  );
}

function ConfigField({
  label,
  value,
  readonly = false,
}: {
  label: string;
  value: string;
  readonly?: boolean;
}) {
  return (
    <div>
      <label className="block text-drt-400 text-sm mb-1">{label}</label>
      <input
        type="text"
        value={value}
        readOnly={readonly}
        className="w-full bg-drt-800 border border-drt-700 rounded px-3 py-2 text-white disabled:opacity-75"
        disabled={readonly}
      />
    </div>
  );
}

function EnvVar({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-drt-400">{label}</span>
      <code className="bg-drt-800 px-2 py-1 rounded text-drt-200 font-mono text-xs">
        {value}
      </code>
    </div>
  );
}
