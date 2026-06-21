"use client";

import { createClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
// Accept either name — Supabase's newer quickstarts call it PUBLISHABLE_KEY, older ones
// (and our .env.example) call it ANON_KEY. Both are the same browser-safe key.
const anon = (process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  ?? process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY)!;

// Single browser client; persists the session in localStorage.
export const supabase = createClient(url, anon, {
  auth: { persistSession: true, autoRefreshToken: true },
});

export async function accessToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}
