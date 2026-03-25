import * as React from "react";
import { LogOut, Menu, PackageSearch, Settings, Shield, Truck } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { useAuthStore } from "@/stores/auth-store";
import { Button } from "@/components/ui/button";

const navItems = [
  { label: "Dashboard", to: "/dashboard", icon: Menu },
  { label: "Shipments", to: "/shipments", icon: Truck },
  { label: "Simulation", to: "/simulation", icon: Settings },
  { label: "Audits", to: "/audits", icon: Shield },
  { label: "Logs", to: "/logs", icon: PackageSearch },
];

export default function Sidebar() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const clearToken = useAuthStore((s) => s.clearToken);

  return (
    <aside className="fixed inset-y-0 left-0 z-40 w-64 border-r bg-sidebar">
      <div className="flex h-full flex-col p-4">
        <div className="mb-6">
          <div className="flex items-center gap-2">
            <div className="h-9 w-9 rounded-md bg-primary text-primary-foreground flex items-center justify-center">
              S
            </div>
            <div className="leading-tight">
              <div className="text-sm font-semibold">Sentinel</div>
              <div className="text-xs opacity-70">Control Cockpit</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.to}
                to={item.to}
                className="flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground"
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-6 space-y-3">
          <div className="text-xs text-muted-foreground">
            Signed in as <span className="font-medium text-foreground">{user?.username ?? "admin"}</span>
          </div>
          <Button
            variant="outline"
            className="w-full justify-center"
            onClick={() => {
              clearToken();
              navigate("/login");
            }}
          >
            <LogOut className="h-4 w-4" />
            Logout
          </Button>
        </div>
      </div>
    </aside>
  );
}

