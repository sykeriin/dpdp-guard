// Thin client for the hosted guard. No local logic: consent state and rules live server-side.
export class Guard {
  constructor({ baseUrl, apiKey, business, requiredPurposes = ["order_updates"], optionalPurposes = [], privacyUrl, fetchImpl = fetch }) {
    Object.assign(this, { baseUrl: baseUrl.replace(/\/$/, ""), apiKey, business, requiredPurposes, optionalPurposes, privacyUrl, fetchImpl });
  }
  /** Run before your agent. If result.action === "forward", pass result.message to the agent; else send result.replyText to the user. */
  async guard(message, userId, channel = "web") {
    const r = await this.fetchImpl(`${this.baseUrl}/v1/guard`, {
      method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${this.apiKey}` },
      body: JSON.stringify({ message, user_id: userId, channel, business: this.business, required_purposes: this.requiredPurposes,
        optional_purposes: this.optionalPurposes, ...(this.privacyUrl && { privacy_url: this.privacyUrl }) }),
    });
    if (!r.ok) throw new Error(`guard failed: ${r.status} ${await r.text()}`);
    const j = await r.json();
    return { action: j.action, message: j.message, maskedMessage: j.masked_message, replyText: j.reply_text, intent: j.intent, granted: j.granted, rightsRef: j.rights_ref, principal: j.principal };
  }
}
