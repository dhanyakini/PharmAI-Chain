import * as React from "react";
import { Link, useNavigate } from "react-router-dom";
import { Eye, EyeOff } from "lucide-react";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/stores/auth-store";

export default function LoginPage() {
  const navigate = useNavigate();
  const setToken = useAuthStore((s) => s.setToken);
  const validateToken = useAuthStore((s) => s.validateToken);

  const [username, setUsername] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [showPassword, setShowPassword] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  const passwordId = React.useId();
  const usernameId = React.useId();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    const u = username.trim();
    if (!u || !password) {
      setError(!u ? "Enter a username." : "Enter a password.");
      setSubmitting(false);
      return;
    }
    try {
      const res = await api.post("/auth/login", { username: u, password });
      const token: string = res.data.access_token;
      setToken(token);
      const ok = await validateToken();
      if (ok) {
        navigate("/dashboard");
      } else {
        setError("Session could not be verified. Try again.");
      }
    } catch (err: unknown) {
      const detail =
        typeof err === "object" &&
        err !== null &&
        "response" in err &&
        typeof (err as { response?: { data?: { detail?: string } } }).response?.data?.detail === "string"
          ? (err as { response: { data: { detail: string } } }).response.data.detail
          : "Login failed";
      setError(detail);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md space-y-4 rounded-lg border bg-card p-6 shadow-sm">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold">Sign in</h1>
          <p className="text-sm text-muted-foreground">
            Sentinel control cockpit — use the account created for your environment.
          </p>
        </div>
        <form className="space-y-3" onSubmit={onSubmit} noValidate>
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor={usernameId}>
              Username
            </label>
            <Input
              id={usernameId}
              name="username"
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? "login-error" : undefined}
              disabled={submitting}
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor={passwordId}>
              Password
            </label>
            <div className="relative">
              <Input
                id={passwordId}
                name="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? "login-error" : undefined}
                className="pr-10"
                disabled={submitting}
              />
              <button
                type="button"
                className="absolute right-0 top-0 flex h-full w-10 items-center justify-center rounded-r-md text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => setShowPassword((v) => !v)}
                tabIndex={-1}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
          {error ? (
            <div id="login-error" className="text-sm text-destructive" role="alert">
              {error}
            </div>
          ) : null}
          <Button type="submit" disabled={submitting} className="w-full" aria-busy={submitting}>
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <p className="text-center text-sm text-muted-foreground">
          <Link to="/" className="underline-offset-4 hover:underline">
            Back to home
          </Link>
        </p>
      </div>
    </div>
  );
}
