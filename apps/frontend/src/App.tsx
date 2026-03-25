import { Navigate, Route, Routes } from "react-router-dom";

import LoginPage from "./pages/login";
import LandingPage from "./pages/landing";
import DashboardPage from "./pages/dashboard";
import ProtectedRoute from "./components/layout/protected-route";
import AppLayout from "./components/layout/app-layout";
import ShipmentsPage from "./pages/shipments";
import ShipmentCreatePage from "./pages/shipment-create";
import ShipmentDetailPage from "./pages/shipment-detail";
import SimulationPage from "./pages/simulation";
import SimulationIndexPage from "./pages/simulation-index";
import AuditsPage from "./pages/audits";
import LogsPage from "./pages/logs";

export default function App() {
  function Placeholder({ title }: { title: string }) {
    return (
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold">{title}</h1>
        <p className="text-sm text-muted-foreground">
          This section will be fully implemented in subsequent phases.
        </p>
      </div>
    );
  }

  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <AppLayout>
              <DashboardPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/shipments"
        element={
          <ProtectedRoute>
            <AppLayout>
              <ShipmentsPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/shipments/new"
        element={
          <ProtectedRoute>
            <AppLayout>
              <ShipmentCreatePage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/shipments/:id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <ShipmentDetailPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/audits"
        element={
          <ProtectedRoute>
            <AppLayout>
              <AuditsPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/simulation/:id"
        element={
          <ProtectedRoute>
            <AppLayout>
              <SimulationPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/simulation"
        element={
          <ProtectedRoute>
            <AppLayout>
              <SimulationIndexPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/logs"
        element={
          <ProtectedRoute>
            <AppLayout>
              <LogsPage />
            </AppLayout>
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
