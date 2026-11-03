import { cookies } from "next/headers";
import { API, COOKIE, secureCookie } from "../../../lib/server";

export async function POST(req) {
  const { key } = await req.json().catch(() => ({}));
  if (!key || typeof key !== "string") return Response.json({ error: "API key required" }, { status: 400 });
  const r = await fetch(`${API}/v1/ledger/verify`, { headers: { Authorization: `Bearer ${key}` }, cache: "no-store" }).catch(() => null);
  if (!r) return Response.json({ error: "Ledger API unreachable" }, { status: 502 });
  if (!r.ok) return Response.json({ error: "Invalid API key" }, { status: 401 });
  (await cookies()).set(COOKIE, key, { httpOnly: true, sameSite: "strict", secure: secureCookie(), path: "/", maxAge: 60 * 60 * 8 });
  return Response.json({ ok: true });
}

export async function DELETE() {
  (await cookies()).delete(COOKIE);
  return Response.json({ ok: true });
}

export async function GET() {   // lets the UI know whether a session exists without exposing the key
  return Response.json({ loggedIn: Boolean((await cookies()).get(COOKIE)) });
}
