import { useEffect, useState } from "react";
import Dashboard from "./components/Dashboard";
import Login from "./components/Login";
import { setSessionExpiredHandler } from "./lib/api";
import { isAuthenticated, logout } from "./lib/auth";
import { useToast } from "./lib/toastContext";

export default function App() {
  const [authed, setAuthed] = useState(isAuthenticated());
  const toast = useToast();

  useEffect(() => {
    setSessionExpiredHandler(() => {
      setAuthed(false);
      toast.info("Session expired", "Your access token could no longer be refreshed — please sign in again.");
    });
    return () => setSessionExpiredHandler(null);
  }, [toast]);

  if (!authed) {
    return <Login onSuccess={() => setAuthed(true)} />;
  }

  return (
    <Dashboard
      onLogout={() => {
        logout();
        setAuthed(false);
      }}
    />
  );
}
