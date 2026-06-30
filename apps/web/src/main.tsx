import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { OriginProvider } from "./origin";
import { EngineProvider } from "./engine";
import { I18nProvider } from "./i18n";
import "./styles.css";

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error, info: any) { console.error("React error:", error, info); }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 32, fontFamily: "monospace" }}>
          <h1 style={{ color: "#dc2626" }}>React Error</h1>
          <pre style={{ whiteSpace: "pre-wrap" }}>
            {this.state.error.message}{"\n\n"}{this.state.error.stack}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchInterval: 60_000 } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={qc}>
        <I18nProvider>
          <OriginProvider>
            <EngineProvider>
              <App />
            </EngineProvider>
          </OriginProvider>
        </I18nProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </React.StrictMode>
);
