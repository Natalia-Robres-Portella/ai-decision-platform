import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";

// Layout is the persistent shell — sidebar stays fixed while the <Outlet>
// (the active page) swaps out. React Router renders child routes into <Outlet>.
export function Layout() {
  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
