// Integration test: needs the API on GUARD_URL and ADMIN_TOKEN. Run: ADMIN_TOKEN=adm node test.mjs
import assert from "node:assert/strict";
import { Guard } from "./index.js";
const url = process.env.GUARD_URL || "http://localhost:8000", id = "node_" + Math.random().toString(36).slice(2, 8);
const { api_key } = await (await fetch(url + "/admin/tenants", { method: "POST", headers: { "Content-Type": "application/json", "X-Admin-Token": process.env.ADMIN_TOKEN || "adm" }, body: JSON.stringify({ id, name: id }) })).json();
const g = new Guard({ baseUrl: url, apiKey: api_key, business: "Acme", requiredPurposes: ["order_updates"], optionalPurposes: ["marketing"] });
assert.equal((await g.guard("hi", "u1", "whatsapp")).action, "reply");
assert.deepEqual((await g.guard("1", "u1")).granted, ["order_updates"]);
const r = await g.guard("my number is 9876543210", "u1");
assert.equal(r.action, "forward"); assert.ok(!r.maskedMessage.includes("9876543210")); assert.ok(r.message.includes("9876543210"));
assert.equal((await g.guard("meri details hatao", "u1")).intent, "erasure");
assert.ok(Array.isArray(r.notify));
const kid = await g.guard("I am 14 years old", "kid"); assert.equal(kid.action, "block");
const inv = await g.guard("my mom is 98765 11111", "kid"); assert.equal(inv.notify.length, 1); assert.equal(inv.notify[0].to, "9876511111");
console.log("node sdk ok");
