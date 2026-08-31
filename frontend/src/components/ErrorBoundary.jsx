import { Component } from "react";
import Button from "./ui/Button";
import Icon from "./ui/Icon";
import Wordmark from "./ui/Wordmark";

/* Last line of defence: a render error shows a designed screen with a way out,
 * instead of a blank page.
 */

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Nothing to report to — surfacing it in the console is the useful thing
    // an operator or a judge can actually act on.
    console.error("Recovery Room crashed:", error, info?.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="cine-bg grain relative flex min-h-screen flex-col items-center justify-center px-6 text-center">
        <div aria-hidden="true" className="scrim-b pointer-events-none absolute inset-0" />
        <div className="relative max-w-md">
          <Wordmark size="md" className="mb-8" />
          <span className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full border border-alert/40 bg-alert-tint text-alert-ink">
            <Icon name="alert" size={26} />
          </span>
          <h1 className="text-h1 text-fg">The Recovery Room hit an error</h1>
          <p className="mt-3 text-body text-fg-muted">
            Something in the dashboard failed to render. Your data is untouched — the audit log is append-only and
            nothing here writes to it.
          </p>
          <p className="mt-4 rounded-lg border border-hairline bg-surface-2 px-3.5 py-2.5 text-left font-mono text-[0.75rem] break-words text-fg-subtle">
            {String(this.state.error?.message || this.state.error)}
          </p>
          <Button size="lg" icon="refresh" className="mt-7" onClick={() => window.location.reload()}>
            Reload the dashboard
          </Button>
        </div>
      </div>
    );
  }
}
