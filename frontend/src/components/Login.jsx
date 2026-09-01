import { useId, useState } from "react";
import { login } from "../lib/auth";
import Button from "./ui/Button";
import Icon from "./ui/Icon";
import Wordmark from "./ui/Wordmark";

const FEATURES = [
  { icon: "activity", text: "Watch every recovery decision land, transaction by transaction" },
  { icon: "shield", text: "Deterministic guardrails, firing live — never an LLM call" },
  { icon: "list", text: "An append-only audit trail you can click all the way down" },
];

export default function Login({ onSuccess }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const userId = useId();
  const passId = useId();
  const errorId = useId();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(username, password);
      onSuccess();
    } catch {
      setError("Invalid username or password.");
    } finally {
      setLoading(false);
    }
  };

  const inputClass =
    "h-12 w-full rounded-lg border border-hairline-strong bg-void/60 px-3.5 text-body text-fg " +
    "placeholder:text-fg-subtle transition-colors duration-200 ease-standard " +
    "hover:border-fg-faint focus:border-brand focus:bg-void/80";

  return (
    <div className="cine-bg grain relative min-h-screen overflow-hidden">
      <div aria-hidden="true" className="scrim-b pointer-events-none absolute inset-0" />

      <div className="relative mx-auto flex min-h-screen w-full max-w-6xl flex-col px-5 py-6 sm:px-8 lg:px-10">
        <header className="flex items-center justify-between">
          <Wordmark size="md" />
          <span className="hidden text-caption uppercase text-fg-subtle sm:block">Razorpay AI Buildathon · Track 03</span>
        </header>

        <main className="flex flex-1 items-center justify-center py-10 lg:py-16">
          <div className="grid w-full items-center gap-12 lg:grid-cols-[1.05fr_auto] lg:gap-16">
            <div className="hidden lg:block">
              <p className="text-caption uppercase text-brand-ink">Autonomous revenue recovery</p>
              <p className="mt-3 text-display text-fg text-balance">
                Revenue at risk,
                <br />
                recovered while you watch.
              </p>
              <p className="mt-5 max-w-lg text-body text-fg-muted">
                RecoverAI detects failing payments, diagnoses the root cause, decides a bounded intervention, and acts —
                logging every step to an audit trail you can replay.
              </p>
              <ul className="mt-8 space-y-3.5">
                {FEATURES.map((f) => (
                  <li key={f.text} className="flex items-start gap-3 text-meta text-fg-muted">
                    <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-hairline bg-surface-2 text-brand-ink">
                      <Icon name={f.icon} size={14} />
                    </span>
                    {f.text}
                  </li>
                ))}
              </ul>
            </div>

            <div className="mx-auto w-full max-w-[26rem]">
              <form
                onSubmit={handleSubmit}
                noValidate
                aria-describedby={error ? errorId : undefined}
                className="glass rounded-2xl border border-hairline-strong p-6 shadow-modal sm:p-8"
              >
                <div className="lg:hidden">
                  <p className="text-caption uppercase text-brand-ink">Autonomous revenue recovery</p>
                </div>
                <h1 className="mt-1 text-h1 text-fg lg:mt-0">Sign in</h1>
                <p className="mt-2 text-meta text-fg-subtle">
                  Operator access only — one seeded account per deployment.
                </p>

                <div className="mt-7 space-y-4">
                  <div>
                    <label htmlFor={userId} className="mb-1.5 block text-caption uppercase text-fg-subtle">
                      Username
                    </label>
                    <input
                      id={userId}
                      name="username"
                      autoFocus
                      autoComplete="username"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      aria-invalid={error ? "true" : undefined}
                      className={inputClass}
                      placeholder="operator"
                    />
                  </div>

                  <div>
                    <label htmlFor={passId} className="mb-1.5 block text-caption uppercase text-fg-subtle">
                      Password
                    </label>
                    <div className="relative">
                      <input
                        id={passId}
                        name="password"
                        type={showPassword ? "text" : "password"}
                        autoComplete="current-password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        aria-invalid={error ? "true" : undefined}
                        className={`${inputClass} pr-12`}
                        placeholder="••••••••"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword((v) => !v)}
                        aria-label={showPassword ? "Hide password" : "Show password"}
                        aria-pressed={showPassword}
                        className="absolute inset-y-0 right-0 grid w-12 place-items-center rounded-r-lg text-fg-subtle transition-colors hover:text-fg"
                      >
                        <Icon name={showPassword ? "eyeOff" : "eye"} size={17} />
                      </button>
                    </div>
                  </div>
                </div>

                {error && (
                  <p
                    id={errorId}
                    role="alert"
                    className="mt-4 flex items-center gap-2 rounded-lg border border-danger/45 bg-danger-tint px-3 py-2.5 text-meta text-danger-ink"
                  >
                    <Icon name="alert" size={15} />
                    {error}
                  </p>
                )}

                <Button type="submit" size="lg" loading={loading} className="mt-6 w-full">
                  {loading ? "Signing in…" : "Sign in"}
                </Button>

                {import.meta.env.DEV && (
                  <p className="mt-5 text-center text-[0.75rem] leading-relaxed text-fg-subtle">
                    No account? Run{" "}
                    <code className="rounded bg-surface-3 px-1.5 py-0.5 font-mono text-[0.6875rem] text-fg-subtle">
                      python manage.py seed_dashboard_user
                    </code>{" "}
                    on the backend.
                  </p>
                )}
              </form>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
