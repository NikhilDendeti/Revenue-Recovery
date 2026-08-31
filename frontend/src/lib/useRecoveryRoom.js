import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { getAccessToken } from "./auth";
import { wsUrl } from "./config";

const MAX_FEED = 120;

// Monotonic across the session. `prev.length` freezes once the feed is clamped to
// MAX_FEED, which would then hand React duplicate keys for every later event.
let feedSeq = 0;

export function useRecoveryRoom() {
  const [summary, setSummary] = useState(null);
  const [ticks, setTicks] = useState([]);
  const [guardrails, setGuardrails] = useState([]);
  const [voiceMoment, setVoiceMoment] = useState(null);
  const [connected, setConnected] = useState(false);
  // Additive: the summary fetch used to swallow every rejection, so a backend
  // that was down looked identical to one with no data. Callers that don't
  // destructure `error` are unaffected.
  const [error, setError] = useState(null);
  const wsRef = useRef(null);

  const refreshSummary = useCallback(() => {
    api
      .summary()
      .then((data) => {
        setSummary(data);
        setError(null);
      })
      .catch(() => setError("Couldn't load the recovery summary."));
  }, []);

  useEffect(() => {
    refreshSummary();

    // The browser WebSocket API can't set an Authorization header, so the access
    // token travels as a query param — see recovery/auth_middleware.py. Grabbed once
    // at connect time; a token that expires mid-connection isn't refreshed (the
    // connection stays open regardless — see design.md's WS non-goals).
    const token = getAccessToken();
    const ws = new WebSocket(wsUrl(`/ws/recovery/?token=${encodeURIComponent(token || "")}`));
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (evt) => {
      let msg;
      try {
        msg = JSON.parse(evt.data);
      } catch {
        return; // a malformed frame shouldn't take the handler down
      }
      if (msg.type === "ticker") {
        setSummary(msg.payload.summary);
        setTicks((prev) =>
          [
            { ...msg.payload, _key: `${msg.payload.transaction_id}-${++feedSeq}`, _receivedAt: new Date().toISOString() },
            ...prev,
          ].slice(0, MAX_FEED)
        );
      } else if (msg.type === "guardrail") {
        setGuardrails((prev) =>
          [{ ...msg.payload, _key: `${msg.payload.transaction_id}-${msg.payload.rule_name}-${++feedSeq}` }, ...prev].slice(
            0,
            MAX_FEED
          )
        );
      } else if (msg.type === "voice") {
        setVoiceMoment(msg.payload);
      }
      // 'audit' events aren't separately buffered here — the Audit Trail panel always
      // reads the full chain fresh via GET /transactions/:id/chain/ on click, which is
      // the source of truth; WS just drives the live feel of the other two panels.
    };

    return () => ws.close();
  }, [refreshSummary]);

  return { summary, ticks, guardrails, voiceMoment, setVoiceMoment, connected, error, refreshSummary };
}
