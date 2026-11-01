import { useEffect, useRef, useState } from "react";
import type { AuthSession } from "../lib/supabaseAuth";
import { personalRequest } from "./api";
import type { Profile, Readiness } from "./types";

export function ReceptionistToggle({ session }: { session: AuthSession }) {
  const [mode, setMode] = useState<Profile["mode"] | null>(null);
  const [available, setAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const revision = useRef(0);
  const pending = useRef(false);
  const mutating = useRef(false);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    let stopped = false;
    const refresh = async () => {
      if (pending.current || mutating.current || document.hidden) return;
      pending.current = true;
      const current = revision.current;
      try {
        const readiness = await personalRequest<Readiness>(session, "/readiness");
        if (!readiness.enabled || !readiness.owner_configured) {
          if (!stopped && current === revision.current) setAvailable(false);
          return;
        }
        const profile = await personalRequest<Profile>(session, "/profile");
        if (!stopped && current === revision.current) {
          setMode(profile.mode);
          setAvailable(readiness.voice_routing_implemented && readiness.voice_configured);
        }
      } catch {
        if (!stopped && current === revision.current) setAvailable(false);
      } finally {
        pending.current = false;
      }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 15000);
    window.addEventListener("focus", refresh);
    return () => {
      stopped = true;
      mounted.current = false;
      revision.current += 1;
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, [session]);

  async function toggle() {
    if (!available || mutating.current || !mode) return;
    mutating.current = true;
    revision.current += 1;
    const current = revision.current;
    setBusy(true);
    setError("");
    try {
      const profile = await personalRequest<Profile>(session, "/mode", "PUT", {
        mode: mode === "receptionist" ? "personal_agent" : "receptionist",
      });
      if (mounted.current && current === revision.current) setMode(profile.mode);
    } catch (caught) {
      if (mounted.current && current === revision.current) {
        setError(caught instanceof Error ? caught.message : "Could not change AI mode.");
      }
    } finally {
      mutating.current = false;
      if (mounted.current && current === revision.current) setBusy(false);
    }
  }

  const on = mode === "receptionist";
  return <div className="receptionist-mode-control">
    <div className="receptionist-mode-row">
      <span id="receptionist-mode-label">AI Receptionist</span>
      <button type="button" role="switch" aria-checked={on}
        aria-labelledby="receptionist-mode-label" aria-describedby="receptionist-mode-status"
        className={`receptionist-mode-switch${on ? " is-on" : ""}`}
        disabled={!available || busy || !mode} onClick={() => void toggle()}
        title={available ? "ON: Receptionist · OFF: Friday for your registered number" : "Personal AI mode setup unavailable"}>
        <span className="receptionist-mode-thumb" />
      </button>
    </div>
    <small id="receptionist-mode-status" aria-live="polite">
      {busy ? "Saving…" : !available ? "Mode unavailable" : on ? "ON · Receptionist active" : "OFF · Friday selected"}
    </small>
    {error && <small className="receptionist-mode-error" role="alert">{error}</small>}
  </div>;
}
