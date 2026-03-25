import * as React from "react";
import { Navigate } from "react-router-dom";

import { useAuthStore } from "@/stores/auth-store";

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const isHydrated = useAuthStore((s) => s.isHydrated);
  const loadingMe = useAuthStore((s) => s.loadingMe);
  const validateToken = useAuthStore((s) => s.validateToken);

  React.useEffect(() => {
    if (!token || user) return;
    void validateToken();
  }, [token, user, validateToken]);

  if (!isHydrated) {
    return <div className="min-h-screen p-6">Loading...</div>;
  }

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  if (loadingMe || !user) {
    return <div className="min-h-screen p-6">Authenticating...</div>;
  }

  return <>{children}</>;
}

