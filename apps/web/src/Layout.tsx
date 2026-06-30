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
