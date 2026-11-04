"use client";
import { useEffect, useState } from "react";
import { BASE } from "../../lib/api";

const NOTICE_VERSION = "waitlist-v1-draft";
export default function Welcome() {
  const [email, setEmail] = useState(""); const [contact, setContact] = useState(false); const [tips, setTips] = useState(false);
  const [done, setDone] = useState(null); const [err, setErr] = useState(""); const [delTok, setDelTok] = useState(""); const [deleted, setDeleted] = useState(false);
  useEffect(() => { setDelTok(new URLSearchParams(location.search).get("delete") || ""); }, []);
  const join = async () => {
    setErr("");
    const r = await fetch(BASE + "/v1/waitlist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, consent_contact: contact, consent_tips: tips }) });
    if (r.ok) setDone(await r.json()); else setErr(r.status === 429 ? "Too many attempts, try again in a minute." : (await r.json().catch(() => ({}))).detail || "Something went wrong.");
  };
  const remove = async () => { const r = await fetch(BASE + "/v1/waitlist?token=" + encodeURIComponent(delTok), { method: "DELETE" }); if (r.ok) setDeleted(true); else setErr("That link is invalid or was already used."); };
  return (<div style={{ maxWidth: 760, margin: "0 auto" }}>
    <h1 style={{ fontSize: 32, lineHeight: 1.2 }}>Make your WhatsApp and voice bots DPDP-ready before 13 May 2027</h1>
    <p className="muted" style={{ fontSize: 17 }}>DPDP Guard sits between your channel and your agent. It asks for consent in the chat, per purpose; masks personal data before it reaches your logs; recognises "delete my data" / "meri details hatao"; erases across your stores; and produces the audit evidence a lawyer asks for.</p>
    <div className="card"><b>Why now.</b> The DPDP Rules were notified in November 2025 and, per published summaries, most obligations (notice, consent, security, breach reporting, data-principal rights) become enforceable in May 2027. Penalties reach ₹250 crore for security failures. Check the Rules text itself; do not rely on this page.</div>
    <div className="grid">
      <div className="card"><b>For agencies and freelancers</b><p className="muted">One SDK call in front of any agent (LangGraph, n8n, raw WhatsApp Cloud API). Sell compliance as a line item to your clients.</p></div>
      <div className="card"><b>For in-house teams</b><p className="muted">Clinics, D2C brands, coaching institutes, small fintechs: the bot is your least-controlled data surface.</p></div>
    </div>
    <div className="card"><b>Free: check one of your bots now.</b> Paste a transcript or flow and get a gap report. Nothing is stored. <div className="row"><a href="/checker"><button>Open the bot checker</button></a></div></div>
    <div className="card"><b>What it is not.</b> Not legal advice, and not a registered Consent Manager. Notices and templates are drafts that need review by your lawyer. Early software: no customers yet, which is why we want to talk to you.</div>

    <h2>Join the pilot waitlist</h2>
    {deleted ? <p className="ok">Done: your signup was deleted.</p> : delTok && !done ? <div className="card"><p>Delete your waitlist signup?</p><button onClick={remove}>Yes, delete it</button><p className="err">{err}</p></div> :
    done ? <div className="card"><p className="ok">You're on the list.</p>
      <p>We stored your email for: {done.purposes.join(", ")}. We keep it for {done.retention_days} days unless you delete it sooner. Delete it anytime with this link (save it, we don't email it to you):</p>
      <p><a href={"/welcome?delete=" + done.delete_token}>{typeof location !== "undefined" ? location.origin : ""}/welcome?delete={done.delete_token}</a></p></div> :
    <div className="card">
      <p className="muted" style={{ marginTop: 0 }}><b>Notice ({NOTICE_VERSION}).</b> We'll use your email to contact you about DPDP Guard pilots and launch. We keep it 365 days or until you delete it. We don't sell or share it. Delete it any time with the link you get after signing up.</p>
      <div className="row"><input type="email" placeholder="you@company.com" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
      <label style={{ display: "block", margin: "6px 0" }}><input type="checkbox" style={{ minWidth: 0, width: "auto", marginRight: 8 }} checked={contact} onChange={(e) => setContact(e.target.checked)} /> Contact me about DPDP Guard pilots and launch (required)</label>
      <label style={{ display: "block", margin: "6px 0" }}><input type="checkbox" style={{ minWidth: 0, width: "auto", marginRight: 8 }} checked={tips} onChange={(e) => setTips(e.target.checked)} /> Also send me occasional DPDP compliance tips (optional, separate)</label>
      <div className="row"><button onClick={join} disabled={!email || !contact}>Join waitlist</button></div><p className="err">{err}</p></div>}
  </div>);
}
