export interface GuardResult { action: "forward" | "reply" | "block"; message: string; maskedMessage: string; replyText: string; intent: string | null; granted: string[]; rightsRef: string | null; notify: { to: string; text: string }[]; principal: string }
export class Guard {
  constructor(o: { baseUrl: string; apiKey: string; business: string; requiredPurposes?: string[]; optionalPurposes?: string[]; privacyUrl?: string; fetchImpl?: typeof fetch });
  guard(message: string, userId: string, channel?: string): Promise<GuardResult>;
}
