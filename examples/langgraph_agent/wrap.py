"""Wrap any LangGraph node/agent: `guarded = with_guard(guard, agent_fn)`. Works with any callable str -> str."""
def with_guard(guard, agent, channel="web"):
    def run(message: str, user_id: str) -> str:
        r = guard(message, user_id, channel)
        return agent(r.message) if r.action == "forward" else r.reply_text
    return run

# LangGraph usage: add a first node that calls guard() and conditionally routes to END with reply_text
#   graph.add_node("guard", lambda s: {"guard": guard(s["input"], s["user_id"])})
#   graph.add_conditional_edges("guard", lambda s: "agent" if s["guard"].action == "forward" else END)
