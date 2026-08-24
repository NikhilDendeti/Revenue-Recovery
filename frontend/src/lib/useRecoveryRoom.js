import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { getAccessToken } from "./auth";

const MAX_FEED = 120;

export function useRecoveryRoom() {
  const [summary, setSummary] = useState(null);
  const [ticks, setTicks] = useState([]);
  const [guardrails, setGuardrails] = useState([]);
  const [voiceMoment, setVoiceMoment] = useState(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);

  const refreshSummary = useCallback(() => {
    api.summary().then(setSummary).catch(() => {});
  }, []);

  useEffect(() => {
    refreshSummary();

    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    // The browser WebSocket API can't set an Authorization header, so the access
    // token travels as a query param — see recovery/auth_middleware.py. Grabbed once
    // at connect time; a token that expires mid-connection isn't refreshed (the
    // connection stays open regardless — see design.md's WS non-goals).
    const token = getAccessToken();
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/recovery/?token=${encodeURIComponent(token || "")}`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.type === "ticker") {
        setSummary(msg.payload.summary);
        setTicks((prev) =>
          [
            { ...msg.payload, _key: `${msg.payload.transaction_id}-${prev.length}`, _receivedAt: new Date().toISOString() },
            ...prev,
          ].slice(0, MAX_FEED)
        );
      } else if (msg.type === "guardrail") {
        setGuardrails((prev) =>
          [{ ...msg.payload, _key: `${msg.payload.transaction_id}-${msg.payload.rule_name}-${prev.length}` }, ...prev].slice(
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

  return { summary, ticks, guardrails, voiceMoment, setVoiceMoment, connected, refreshSummary };
}
