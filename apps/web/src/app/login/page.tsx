"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { useSession } from "@/lib/useSession";

export default function LoginPage() {
  const router = useRouter();
  const { session } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (session) router.replace("/matches");
  }, [session, router]);

  async function signIn(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    setBusy(false);
    if (error) setMsg(error.message);
    else router.replace("/matches");
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <form onSubmit={signIn} className="ps-card w-full max-w-sm p-8 space-y-4">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center text-xl ps-btn-grad">🏡</div>
          <div>
            <div className="text-lg font-extrabold bg-clip-text text-transparent"
                 style={{ backgroundImage: "var(--grad)" }}>prop-search</div>
            <div className="text-xs text-[var(--color-muted)] font-semibold">Noida kothi finder</div>
          </div>
        </div>
        <input
          type="email" placeholder="Email" value={email} required
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-xl border border-[var(--color-line)] px-3 py-2 outline-none focus:border-[var(--color-brand)]"
        />
        <input
          type="password" placeholder="Password" value={password} required
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-xl border border-[var(--color-line)] px-3 py-2 outline-none focus:border-[var(--color-brand)]"
        />
        {msg && <p className="text-sm text-red-600">{msg}</p>}
        <button type="submit" disabled={busy}
          className="ps-btn-grad w-full rounded-xl py-2.5 font-bold disabled:opacity-60">
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
