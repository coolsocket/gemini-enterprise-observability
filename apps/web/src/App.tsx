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

import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./Layout";

const Overview      = lazy(() => import("./pages/Overview"));
const Conversations = lazy(() => import("./pages/Conversations"));
const Files         = lazy(() => import("./pages/Files"));
const Persona       = lazy(() => import("./pages/Persona"));
const Builders      = lazy(() => import("./pages/Builders"));
const Activity      = lazy(() => import("./pages/Activity"));
const DataAccess    = lazy(() => import("./pages/DataAccess"));
const UserDeepDive  = lazy(() => import("./pages/UserDeepDive"));
const Agents        = lazy(() => import("./pages/Agents"));
const Engines       = lazy(() => import("./pages/Engines"));
const Quota         = lazy(() => import("./pages/Quota"));
const Raw           = lazy(() => import("./pages/Raw"));
const Settings      = lazy(() => import("./pages/Settings"));

function PageFallback() {
  return (
    <div className="flex items-center justify-center py-16 text-ink-muted text-sm">
      <span className="w-2 h-2 rounded-full bg-accent animate-pulse-dot mr-2" />
      加载中…
    </div>
  );
}

const page = (El: React.ComponentType) => (
  <Suspense fallback={<PageFallback />}><El /></Suspense>
);

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="/overview"      element={page(Overview)} />
          <Route path="/conversations" element={page(Conversations)} />
          <Route path="/files"         element={page(Files)} />
          <Route path="/persona"       element={page(Persona)} />
          <Route path="/user"          element={page(UserDeepDive)} />
          <Route path="/user/:email"   element={page(UserDeepDive)} />
          <Route path="/agents"        element={page(Agents)} />
          <Route path="/agent/:agentId" element={page(Agents)} />
          <Route path="/engines"       element={page(Engines)} />
          <Route path="/quota"         element={page(Quota)} />
          <Route path="/builders"    element={page(Builders)} />
          <Route path="/data-access" element={page(DataAccess)} />
          <Route path="/activity"    element={page(Activity)} />
          <Route path="/raw"         element={page(Raw)} />
          <Route path="/settings"    element={page(Settings)} />
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
