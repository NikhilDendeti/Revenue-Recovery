import { useCallback, useEffect, useState } from "react";
import Header from "./Header";
import SummaryStrip from "./SummaryStrip";
import RecoveryTicker from "./RecoveryTicker";
import GuardrailConsole from "./GuardrailConsole";
import AuditTrail from "./AuditTrail";
import ChainDrawer from "./ChainDrawer";
import VoiceMoment from "./VoiceMoment";
import { api } from "../lib/api";
import { useRecoveryRoom } from "../lib/useRecoveryRoom";

export default function Dashboard({ onLogout }) {
  const { summary, ticks, guardrails, voiceMoment, setVoiceMoment, connected } = useRecoveryRoom();
  const [transactions, setTransactions] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [replaying, setReplaying] = useState(false);

  const refreshTransactions = useCallback(() => {
    api
      .transactions()
      .then((data) => setTransactions(data.results ?? data))
      .catch(() => {});
  }, []);

  useEffect(() => {
    refreshTransactions();
  }, [refreshTransactions]);

  // Cheap live refresh: re-pull the transaction table whenever a new ticker event
  // lands, so the Audit Trail panel's status column stays in sync with the ticker.
  useEffect(() => {
    if (ticks.length > 0) refreshTransactions();
  }, [ticks.length, refreshTransactions]);

  const handleReplay = async () => {
    setReplaying(true);
    try {
      await api.replayBatch();
    } finally {
      setTimeout(() => setReplaying(false), 2000);
    }
  };

  const handleVoiceShowcase = (id) => {
    api.voiceShowcase(id).catch(() => {});
  };

  return (
    <div className="min-h-screen">
      <Header connected={connected} replaying={replaying} onReplay={handleReplay} onLogout={onLogout} />
      <SummaryStrip summary={summary} />
      <VoiceMoment moment={voiceMoment} onDismiss={() => setVoiceMoment(null)} />

      <main className="grid gap-4 px-6 pb-10 sm:px-10 lg:grid-cols-2">
        <RecoveryTicker ticks={ticks} onSelect={setSelectedId} />
        <GuardrailConsole events={guardrails} onSelect={setSelectedId} />
        <div className="lg:col-span-2">
          <AuditTrail transactions={transactions} selectedId={selectedId} onSelect={setSelectedId} />
        </div>
      </main>

      <ChainDrawer transactionId={selectedId} onClose={() => setSelectedId(null)} onVoiceShowcase={handleVoiceShowcase} />
    </div>
  );
}
