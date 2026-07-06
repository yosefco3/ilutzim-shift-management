/**
 * App-wide error boundary.
 *
 * Without this, any render-time exception leaves an empty #root — which inside
 * Telegram's WebView looks like a "blank dark screen". Here we catch it and show
 * a readable message (and log details) instead of failing silently.
 */
import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Surfaced in the WebView console for diagnosis.
    console.error("App crashed:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div
          dir="rtl"
          style={{
            padding: "24px",
            margin: "16px",
            background: "#fff",
            color: "#222",
            borderRadius: "12px",
            fontFamily: "system-ui, sans-serif",
            textAlign: "center",
          }}
        >
          <h2 style={{ margin: "0 0 8px" }}>אירעה שגיאה בטעינת המסך</h2>
          <p style={{ margin: "0 0 16px", color: "#666" }}>
            נסה לרענן. אם זה חוזר — סגור ופתח מחדש דרך הבוט.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            style={{
              padding: "10px 20px",
              border: "none",
              borderRadius: "8px",
              background: "#3390ec",
              color: "#fff",
              fontSize: "16px",
            }}
          >
            רענן
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
