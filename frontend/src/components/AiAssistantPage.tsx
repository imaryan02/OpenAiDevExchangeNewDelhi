import { FormEvent, useState } from "react";
import { Badge, Button, Input, Spinner } from "@fluentui/react-components";
import { SendRegular } from "@fluentui/react-icons";

import { restoreSession } from "../lib/supabaseAuth";

type Message = { role: "assistant" | "user"; text: string; toolCalls?: number };

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export function AiAssistantPage({ organizationId, onDataChange }: { organizationId: string; onDataChange: () => Promise<void> }) {
  const [threadId] = useState(() => crypto.randomUUID());
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "Hello. I can check availability, book a linked patient or create a family profile after complete confirmation, and show upcoming appointments after WhatsApp verification.",
    },
  ]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);

  async function send(event: FormEvent) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || loading) return;
    setDraft("");
    setMessages((current) => [...current, { role: "user", text: message }]);
    setLoading(true);
    try {
      const session = await restoreSession();
      if (!session) throw new Error("Your session expired. Sign in again.");
      const response = await fetch(`${apiBaseUrl}/v1/agent/chat`, {
        method: "POST",
        headers: { Authorization: `Bearer ${session.access_token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ organization_id: organizationId, thread_id: threadId, message }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(payload?.message ?? "The AI preview could not respond.");
      setMessages((current) => [
        ...current,
        { role: "assistant", text: payload.reply, toolCalls: payload.tool_calls },
      ]);
      if (payload.data_changed === true) await onDataChange();
    } catch (error) {
      setMessages((current) => [
        ...current,
        { role: "assistant", text: error instanceof Error ? error.message : "The AI preview could not respond." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return <div className="page-stack ai-assistant-page">
    <section className="assistant-heading">
      <div><span className="assistant-stage">Staff preview · Phase 3</span><h2>AI receptionist</h2><p>Test English, Hindi, or Hinglish with availability and verified appointment recall.</p></div>
      <Badge appearance="tint" color="success">LangGraph · guarded booking</Badge>
    </section>
    <section className="assistant-workspace">
      <aside className="assistant-guardrails">
        <h3>What this preview can do</h3>
        <ul>
          <li>Checks current availability from the clinic schedule.</li>
          <li>Recognizes one unique caller mobile and linked family profiles.</li>
          <li>Books linked patients or creates a family profile after a full offer read-back and explicit yes.</li>
          <li>Sends an OTP before showing upcoming appointment records.</li>
          <li>Cancellation and rescheduling still stay with reception.</li>
          <li>Does not provide medical advice or expose records from caller ID alone.</li>
        </ul>
        <small>Conversation state is isolated to this clinic and browser session.</small>
      </aside>
      <div className="assistant-chat">
        <div className="assistant-messages">
          {messages.map((message, index) => <article className={`assistant-message ${message.role}`} key={`${message.role}-${index}`}>
            <span>{message.role === "assistant" ? "AI reception" : "You"}</span>
            <p>{message.text.replace(/\*\*/g, "")}</p>
            {message.toolCalls ? <small>Used {message.toolCalls} verified lookup{message.toolCalls === 1 ? "" : "s"}</small> : null}
          </article>)}
          {loading && <div className="assistant-thinking"><Spinner size="tiny" /> Checking verified clinic records…</div>}
        </div>
        <form onSubmit={send} className="assistant-composer">
          <Input value={draft} onChange={(_, data) => setDraft(data.value)} placeholder="Example: Dr Amit Sharma available tomorrow?" disabled={loading} />
          <Button appearance="primary" icon={<SendRegular />} type="submit" disabled={loading || !draft.trim()}>Send</Button>
        </form>
      </div>
    </section>
  </div>;
}
