"use client";
import { useEffect, useState } from "react";
export const BASE = "/api/guard";   // same-origin proxy; the API key lives in an httpOnly cookie and never reaches this code
export async function api(path, opts = {}) {
  const r = await fetch(BASE + path, { ...opts, headers: { "Content-Type": "application/json", ...(opts.headers || {}) } });
  if (!r.ok) {
    if (r.status === 401) throw new Error("Not logged in. Go to Overview and enter your API key.");
    throw new Error(`${r.status} ${await r.text()}`);
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r;
}
export function useApi(path, deps = []) {
  const [data, setData] = useState(null); const [err, setErr] = useState(null);
  const reload = () => api(path).then((d) => { setData(d); setErr(null); }).catch((e) => setErr(e.message));
  useEffect(() => { reload(); }, deps); // eslint-disable-line
  return { data, err, reload };
}
export function Table({ rows, cols }) {
  if (!rows) return <p className="muted">Loading…</p>;
  if (!rows.length) return <p className="muted">Nothing here yet.</p>;
  return (<table><thead><tr>{cols.map((c) => <th key={c[0]}>{c[1]}</th>)}</tr></thead>
    <tbody>{rows.map((r, i) => <tr key={i}>{cols.map((c) => <td key={c[0]}>{c[2] ? c[2](r) : String(r[c[0]] ?? "")}</td>)}</tr>)}</tbody></table>);
}
export const Err = ({ e }) => e ? <p className="err">{e}</p> : null;
