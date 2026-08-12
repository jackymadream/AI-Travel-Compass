"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";

import { SiteNav } from "@/components/site-nav";
import { Button } from "@/components/ui/button";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const configured = isSupabaseConfigured();

  async function handleMagicLink(e: FormEvent) {
    e.preventDefault();
    if (!configured) return;
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const supabase = createClient();
      const origin = window.location.origin;
      const { error: authError } = await supabase.auth.signInWithOtp({
        email,
        options: { emailRedirectTo: `${origin}/auth/callback` },
      });
      if (authError) throw authError;
      setMessage("Check your email for the magic link.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Magic link failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogle() {
    if (!configured) return;
    setLoading(true);
    setError(null);
    try {
      const supabase = createClient();
      const origin = window.location.origin;
      const { error: authError } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: `${origin}/auth/callback` },
      });
      if (authError) throw authError;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Google sign-in failed");
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-lg px-4 py-12">
      <SiteNav active="planner" />
      <h1 className="mt-8 font-[family-name:var(--font-display)] text-4xl tracking-tight">
        Sign in
      </h1>
      <p className="mt-2 text-[var(--muted-foreground)]">
        Google OAuth or magic link via Supabase Auth. Required to save itineraries.
      </p>

      {!configured ? (
        <p className="mt-6 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm">
          Set <code>NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
          <code>NEXT_PUBLIC_SUPABASE_ANON_KEY</code> in Vercel / local env to enable
          auth.
        </p>
      ) : (
        <div className="mt-8 space-y-4">
          <Button
            type="button"
            className="w-full"
            disabled={loading}
            onClick={() => {
              void handleGoogle();
            }}
          >
            Continue with Google
          </Button>

          <form onSubmit={handleMagicLink} className="space-y-3">
            <label className="block text-sm font-medium" htmlFor="email">
              Email magic link
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-[var(--border)] bg-[var(--card)] px-3 py-2 text-sm"
              placeholder="you@example.com"
            />
            <Button type="submit" variant="secondary" className="w-full" disabled={loading}>
              Send magic link
            </Button>
          </form>

          {message ? (
            <p className="text-sm text-[var(--primary)]">{message}</p>
          ) : null}
          {error ? (
            <p className="text-sm text-red-600">{error}</p>
          ) : null}
        </div>
      )}

      <p className="mt-8 text-sm text-[var(--muted-foreground)]">
        <Link href="/planner" className="underline underline-offset-2">
          Back to planner
        </Link>
      </p>
    </main>
  );
}
