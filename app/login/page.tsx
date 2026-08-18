"use client";

import { FormEvent, Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { SiteNav } from "@/components/site-nav";
import { Button } from "@/components/ui/button";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";
import { useTranslations } from "next-intl";

function safeNextPath(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) {
    return "/itineraries";
  }
  return raw;
}

function LoginForm() {
  const t = useTranslations("login");
  const searchParams = useSearchParams();
  const nextPath = useMemo(
    () => safeNextPath(searchParams.get("next")),
    [searchParams]
  );
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const configured = isSupabaseConfigured();

  function authCallbackUrl(origin: string): string {
    const callback = new URL("/auth/callback", origin);
    callback.searchParams.set("next", nextPath);
    return callback.toString();
  }

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
        options: { emailRedirectTo: authCallbackUrl(origin) },
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
        options: { redirectTo: authCallbackUrl(origin) },
      });
      if (authError) throw authError;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Google sign-in failed");
      setLoading(false);
    }
  }

  return (
    <>
      <h1 className="mt-8 font-[family-name:var(--font-display)] text-4xl tracking-tight">
        {t("title")}
      </h1>
      <p className="mt-2 text-[var(--muted-foreground)]">
        {t("subtitle")}
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
            {t("google")}
          </Button>

          <form onSubmit={handleMagicLink} className="space-y-3">
            <label className="block text-sm font-medium" htmlFor="email">
              {t("magic")}
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
              {t("send")}
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
          {t("back")}
        </Link>
      </p>
    </>
  );
}

export default function LoginPage() {
  return (
    <main className="mx-auto max-w-lg px-4 py-12">
      <SiteNav active="itineraries" />
      <Suspense fallback={<p className="mt-8 text-sm text-[var(--muted-foreground)]">Loading…</p>}>
        <LoginForm />
      </Suspense>
    </main>
  );
}
