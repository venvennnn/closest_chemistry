"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Logo } from "@/components/logo";
import { supabaseBrowser, supabaseConfigError } from "@/lib/supabase";

export default function HomePage() {
  const router = useRouter();
  const configError = supabaseConfigError();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const client = supabaseBrowser();
    if (!client) return;
    client.auth.getSession().then(({ data }) => {
      if (data.session) router.replace("/app");
    });
  }, [router]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const client = supabaseBrowser();
    if (!client) return;
    setBusy(true);
    setMessage(null);
    const fn =
      mode === "signin"
        ? client.auth.signInWithPassword({ email, password })
        : client.auth.signUp({ email, password });
    const { error } = await fn;
    setBusy(false);
    if (error) {
      setMessage(error.message);
      return;
    }
    if (mode === "signup") {
      setMessage("Check your email if confirmation is enabled, then sign in.");
      return;
    }
    router.replace("/app");
  }

  return (
    <main className="min-h-screen bg-white">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <Logo />
        <p className="text-sm text-muted">Rule-qualified outfit options, not guaranteed wear.</p>
      </header>
      <section className="mx-auto grid max-w-6xl gap-16 px-6 pb-20 pt-10 md:grid-cols-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-pink">Hot pink / the wardrobe canvas</p>
          <h1 className="mt-4 text-5xl font-semibold leading-[1.05] tracking-tight">
            Discover what clicks
            <br />
            in your closet.
          </h1>
          <p className="mt-5 max-w-md text-lg text-muted">
            See which purchases unlock the most distinct, rule-qualified outfit options with clothes you already own.
          </p>
        </div>
        <form onSubmit={submit} className="rounded-3xl border border-[#f1f2f4] p-8 shadow-sm">
          <h2 className="text-xl font-semibold">{mode === "signin" ? "Sign in" : "Create account"}</h2>
          {configError && <p className="mt-4 rounded-xl bg-pink-soft p-3 text-sm text-pink">{configError}</p>}
          <label className="mt-6 block text-sm font-medium">Email</label>
          <input
            className="mt-1 w-full rounded-xl border border-[#ececec] px-3 py-2"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
          <label className="mt-4 block text-sm font-medium">Password</label>
          <input
            className="mt-1 w-full rounded-xl border border-[#ececec] px-3 py-2"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          {message && <p className="mt-4 text-sm text-coral">{message}</p>}
          <button
            disabled={busy || Boolean(configError)}
            className="mt-6 w-full rounded-full bg-pink py-3 font-medium text-white disabled:opacity-50"
          >
            {busy ? "Working…" : mode === "signin" ? "Continue" : "Create account"}
          </button>
          <button
            type="button"
            className="mt-3 w-full text-sm text-muted"
            onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
          >
            {mode === "signin" ? "Need an account?" : "Already have an account?"}
          </button>
        </form>
      </section>
    </main>
  );
}
