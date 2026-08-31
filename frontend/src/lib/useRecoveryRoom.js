import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { getAccessToken } from "./auth";
import { wsUrl } from "./config";

const MAX_FEED = 120;

let feedSeq = 0;

export function useRecoveryRoom() {
  const [summary, setSummary] = useState(null);
  const [ticks, setTicks] = useState([]);
  const [guardrails, setGuardrails] = useState([]);
  const [voiceMoment, setVoiceMoment] = useState(null);
  const [connected, setConnected] = useState(false);
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
        return;
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
    };

    return () => ws.close();
  }, [refreshSummary]);

  return { summary, ticks, guardrails, voiceMoment, setVoiceMoment, connected, error, refreshSummary };
}
