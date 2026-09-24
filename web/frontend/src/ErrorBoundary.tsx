import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/** Nothing in this app previously caught a render-time throw -- one bad
 * array access (e.g. `TimeScrubber`'s scrubber index outliving a repo
 * switch to a repo with fewer snapshots) unmounted the whole tree to a
 * blank page, recoverable only by a full reload. This scopes that recovery
 * to "reload the app in place" instead. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    console.error("cdp web: uncaught render error", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div
          className="flex h-screen w-screen flex-col items-center justify-center gap-3 text-sm"
          style={{ background: "var(--atlas-bg)", color: "var(--atlas-text)" }}
        >
          <div>Something went wrong: {this.state.error.message}</div>
          <button
            className="atlas-card rounded px-3 py-1.5"
            onClick={() => this.setState({ error: null })}
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
