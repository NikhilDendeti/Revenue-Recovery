import { useEffect, useState } from "react";
import Dashboard from "./components/Dashboard";
import Login from "./components/Login";
import { setSessionExpiredHandler } from "./lib/api";
import { isAuthenticated, logout } from "./lib/auth";

export default function App() {
  const [authed, setAuthed] = useState(isAuthenticated());

  useEffect(() => {
    setSessionExpiredHandler(() => setAuthed(false));
    return () => setSessionExpiredHandler(null);
  }, []);

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
