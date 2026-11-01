"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Studio } from "@/components/studio";
import { supabaseBrowser, supabaseConfigError } from "@/lib/supabase";

export default function AppPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState<string | undefined>();
  const configError = supabaseConfigError();

  useEffect(() => {
    const client = supabaseBrowser();
    if (!client) return;
    client.auth.getSession().then(({ data }) => {
      if (!data.session) {
        router.replace("/");
        return;
      }
      setToken(data.session.access_token);
      setEmail(data.session.user.email);
    });
    const { data } = client.auth.onAuthStateChange((_event, session) => {
      if (!session) router.replace("/");
      else setToken(session.access_token);
    });
    return () => data.subscription.unsubscribe();
  }, [router]);

  if (configError) {
    return <p className="p-10 text-pink">{configError}</p>;
  }
  if (!token) return <p className="p-10 text-muted">Checking session…</p>;

  return (
    <Studio
      token={token}
      email={email}
      onSignOut={async () => {
        await supabaseBrowser()?.auth.signOut();
        router.replace("/");
      }}
    />
  );
}
