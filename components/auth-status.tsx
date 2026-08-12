"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { User } from "@supabase/supabase-js";

import { Button } from "@/components/ui/button";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

export function AuthStatus() {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const configured = isSupabaseConfigured();

  useEffect(() => {
    if (!configured) {
      setReady(true);
      return;
    }
    const supabase = createClient();
    void supabase.auth.getUser().then(({ data }) => {
      setUser(data.user);
      setReady(true);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => {
      setUser(session?.user ?? null);
    });
    return () => {
      sub.subscription.unsubscribe();
    };
  }, [configured]);

  if (!ready) {
    return null;
  }

  if (!configured) {
    return (
      <span className="text-xs text-[var(--muted-foreground)]">Auth not configured</span>
    );
  }

  if (!user) {
    return (
      <Button asChild variant="secondary" size="sm">
        <Link href="/login">Sign in</Link>
      </Button>
    );
  }

  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="max-w-[10rem] truncate text-[var(--muted-foreground)]">
        {user.email}
      </span>
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={() => {
          void createClient().auth.signOut();
        }}
      >
        Sign out
      </Button>
    </div>
  );
}
