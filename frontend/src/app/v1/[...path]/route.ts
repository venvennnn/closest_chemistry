import { type NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

const FORWARD = ["authorization", "cookie", "x-session-id", "idempotency-key", "accept"];

function backendOrigin() {
  return (process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
}

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const target = `${backendOrigin()}/v1/${path.join("/")}${req.nextUrl.search}`;
  const method = req.method.toUpperCase();
  const headers = new Headers();
  for (const name of FORWARD) {
    const value = req.headers.get(name);
    if (value) headers.set(name, value);
  }
  const init: RequestInit = { method, headers, cache: "no-store", redirect: "manual" };
  if (method !== "GET" && method !== "HEAD") {
    const contentType = req.headers.get("content-type") || "";
    if (contentType.includes("multipart/form-data")) {
      const incoming = await req.formData();
      const outbound = new FormData();
      incoming.forEach((value, key) => outbound.append(key, value));
      init.body = outbound;
    } else {
      const jsonType = req.headers.get("content-type");
      if (jsonType) headers.set("content-type", jsonType);
      init.body = await req.arrayBuffer();
    }
  }
  try {
    const res = await fetch(target, init);
    const out = new Headers();
    res.headers.forEach((value, key) => {
      const lower = key.toLowerCase();
      if (lower === "content-encoding" || lower === "transfer-encoding" || lower === "content-length") return;
      out.set(key, value);
    });
    return new Response(res.body, { status: res.status, statusText: res.statusText, headers: out });
  } catch {
    return Response.json(
      {
        detail:
          `Cannot reach the Closest Chemistry API at ${backendOrigin()}. ` +
          "Start FastAPI on that origin, or set API_URL (Vercel server env) to your Railway/Render API.",
      },
      { status: 502 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const OPTIONS = proxy;
