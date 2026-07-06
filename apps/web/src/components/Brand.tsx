// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Brand mark: simple "observability lens" — concentric circles + crosshair.
// Generic geometric icon, no third-party brand reference.

export default function Brand({ collapsed }: { collapsed?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <ObsLens className="w-8 h-8 shrink-0" />
      {!collapsed && (
        <div className="min-w-0">
          <div className="text-sm font-semibold text-ink-primary leading-tight">
            GE Observability
          </div>
          <div className="text-[11px] text-ink-muted leading-tight font-mono truncate">
            adoption · audit
          </div>
        </div>
      )}
    </div>
  );
}

function ObsLens({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} xmlns="http://www.w3.org/2000/svg" fill="none">
      <defs>
        <linearGradient id="obs-lens-gradient" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#2dd4bf" />
          <stop offset="1" stopColor="#3b82f6" />
        </linearGradient>
      </defs>
      {/* Outer ring */}
      <circle cx="12" cy="12" r="9.5" stroke="url(#obs-lens-gradient)" strokeWidth="1.8" />
      {/* Crosshair ticks */}
      <line x1="12" y1="1.5" x2="12" y2="4.5"   stroke="url(#obs-lens-gradient)" strokeWidth="1.8" strokeLinecap="round" />
      <line x1="12" y1="19.5" x2="12" y2="22.5" stroke="url(#obs-lens-gradient)" strokeWidth="1.8" strokeLinecap="round" />
      <line x1="1.5" y1="12" x2="4.5" y2="12"   stroke="url(#obs-lens-gradient)" strokeWidth="1.8" strokeLinecap="round" />
      <line x1="19.5" y1="12" x2="22.5" y2="12" stroke="url(#obs-lens-gradient)" strokeWidth="1.8" strokeLinecap="round" />
      {/* Inner pulse */}
      <circle cx="12" cy="12" r="3.2" fill="url(#obs-lens-gradient)" />
    </svg>
  );
}
