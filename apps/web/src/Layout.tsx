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

import { Outlet } from "react-router-dom";
import Header from "./components/Header";
import Sidebar from "./components/Sidebar";

export default function Layout() {
  return (
    <div className="min-h-screen flex bg-canvas">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 canvas-grid">
        <Header />
        <main className="flex-1 px-8 pb-12 max-w-[1400px] w-full">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
