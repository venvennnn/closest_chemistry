import { createClient, type SupabaseClient } from "@supabase/supabase-js";

export function supabaseBrowser(): SupabaseClient | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return null;
  return createClient(url, key, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  });
}

export function supabaseConfigError(): string | null {
  if (!process.env.NEXT_PUBLIC_SUPABASE_URL || !process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY) {
    return "NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are required for sign-in. Create a Supabase project, enable Email auth, and paste the anon key.";
  }
  if (!process.env.NEXT_PUBLIC_API_URL) {
    return "NEXT_PUBLIC_API_URL is required so the browser can reach the FastAPI backend.";
  }
  return null;
}
