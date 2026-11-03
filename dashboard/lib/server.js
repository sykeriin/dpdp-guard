export const API = process.env.GUARD_API_URL || "http://localhost:8000";
export const COOKIE = "dg_session";
// Secure cookies by default in production builds; set INSECURE_COOKIES=1 only for plain-http local demos on non-Chromium browsers.
export const secureCookie = () => process.env.NODE_ENV === "production" && process.env.INSECURE_COOKIES !== "1";
