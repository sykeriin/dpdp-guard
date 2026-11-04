"use client";
import { usePathname } from "next/navigation";
const links = [["/", "Overview"], ["/consents", "Consents"], ["/rights", "Rights queue"], ["/erasure", "Erasure"], ["/breaches", "Breach kit"], ["/audit", "Audit pack"], ["/connectors", "Connectors"], ["/lookup", "Principal lookup"], ["/notices", "Notices"], ["/checker", "Bot checker"]];
export default function Nav() {
  if (usePathname() === "/welcome") return null;          // public page: no dashboard chrome
  return <nav><b>DPDP Guard</b>{links.map(([h, t]) => <a key={h} href={h}>{t}</a>)}</nav>;
}
