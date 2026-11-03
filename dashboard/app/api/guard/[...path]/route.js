import { cookies } from "next/headers";
import { API, COOKIE } from "../../../../lib/server";

// Same-origin proxy: the browser never sees the API key; it lives in an httpOnly cookie.
async function proxy(req, { params }) {
  const { path } = await params;
  const url = new URL(req.url);
  if (req.method !== "GET" && req.method !== "HEAD") {          // CSRF defence in depth on top of SameSite=Strict
    const origin = req.headers.get("origin");
    if (origin && new URL(origin).host !== req.headers.get("host")) return Response.json({ error: "bad origin" }, { status: 403 });
  }
  const key = (await cookies()).get(COOKIE)?.value;
  const headers = { "Content-Type": req.headers.get("content-type") || "application/json" };
  if (key) headers.Authorization = `Bearer ${key}`;
  const body = ["GET", "HEAD"].includes(req.method) ? undefined : await req.arrayBuffer();
  const r = await fetch(`${API}/${path.join("/")}${url.search}`, { method: req.method, headers, body, cache: "no-store" }).catch(() => null);
  if (!r) return Response.json({ error: "Ledger API unreachable" }, { status: 502 });
  const out = new Headers();
  for (const h of ["content-type", "content-disposition"]) if (r.headers.get(h)) out.set(h, r.headers.get(h));
  return new Response(await r.arrayBuffer(), { status: r.status, headers: out });
}
export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE };
