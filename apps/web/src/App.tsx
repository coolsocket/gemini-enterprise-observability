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
