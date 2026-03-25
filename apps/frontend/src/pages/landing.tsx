import * as React from "react";
import { useNavigate } from "react-router-dom";

import { useAuthStore } from "@/stores/auth-store";
import { Button } from "@/components/ui/button";

export default function LandingPage() {
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.token);

  React.useEffect(() => {
    if (token) navigate("/dashboard");
  }, [token, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-2xl space-y-4 rounded-lg border bg-card p-8">
        <h1 className="text-3xl font-semibold">Project Sentinel</h1>
        <p className="text-sm text-muted-foreground">
          A logistics command center for cold-chain simulation with telemetry, weather disruptions, and
          user-controlled rerouting.
        </p>
        <div className="flex gap-3">
          <Button onClick={() => navigate("/login")}>Get Started</Button>
        </div>
      </div>
    </div>
  );
}

