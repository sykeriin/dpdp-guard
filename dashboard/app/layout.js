import "./globals.css";
export const metadata = { title: "DPDP Guard" };
const links = [["/", "Overview"], ["/consents", "Consents"], ["/rights", "Rights queue"], ["/erasure", "Erasure"], ["/breaches", "Breach kit"], ["/audit", "Audit pack"], ["/checker", "Bot checker"]];
export default function Root({ children }) {
  return (<html lang="en"><body><nav><b>DPDP Guard</b>{links.map(([h, t]) => <a key={h} href={h}>{t}</a>)}</nav><main>{children}</main></body></html>);
}
