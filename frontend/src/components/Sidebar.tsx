import { FileText, MessageSquare, Activity, FlaskConical } from "lucide-react";
import { NavLink } from "react-router-dom";

const NAV = [
  { to: "/ingest", icon: FileText, label: "Documents" },
  { to: "/chat", icon: MessageSquare, label: "Ask" },
  { to: "/eval", icon: FlaskConical, label: "Evaluation" },
];

export function Sidebar() {
  return (
    <aside className="flex h-screen w-60 flex-shrink-0 flex-col bg-slate-900">
      {/* Brand */}
      <div className="px-6 pb-4 pt-7">
        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-400">
          AI Decision
        </p>
        <p className="mt-0.5 text-sm font-medium text-white">Intelligence Platform</p>
      </div>

      {/* Divider */}
      <div className="mx-6 border-t border-slate-800" />

      {/* Navigation */}
      <nav className="mt-3 flex-1 px-3">
        {NAV.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              [
                "flex items-center gap-3 rounded px-3 py-2.5 text-sm font-medium transition-colors",
                isActive
                  ? "border-l-2 border-blue-500 bg-slate-800 pl-[10px] text-white"
                  : "border-l-2 border-transparent text-slate-400 hover:bg-slate-800/60 hover:text-slate-200",
              ].join(" ")
            }
          >
            <Icon size={16} strokeWidth={1.75} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="mx-6 border-t border-slate-800 py-4">
        <div className="flex items-center gap-2 text-slate-500">
          <Activity size={12} />
          <span className="text-[11px]">v0.1.0 · gpt-4o-mini</span>
        </div>
      </div>
    </aside>
  );
}
