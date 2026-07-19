/**
 * Procedure reading page — the guard WebApp for a single procedure (סד"פ).
 *
 * Mirror of SubmitPage's guard-WebApp pattern: no navbar, ``useTelegram`` for the
 * initData + WebApp lifecycle, ``guardApiClient`` for the (initData-headered)
 * calls. Renders the sanitized rich HTML (``body_html``) converted from the
 * uploaded docx, or — for pre-feature / pasted-text procedures — a fallback that
 * turns ``body_text`` + ``*bold*`` markers into paragraphs + ``<strong>``.
 * Records a read receipt on first open (server-side, best-effort). The bottom
 * button starts the quiz in chat (first poll sent) and closes the WebApp.
 *
 * RTL, friendly Hebrew error screens (never a raw error). [EDGE A1/A2, D1, D2, I1]
 */
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import { getProcedure, startProcedureQuiz } from '../api/guardApiClient.js';
import { useTelegram } from '../hooks/useTelegram.js';
import { messages } from '../utils/guardMessages.js';
import '../styles/guard.css';

/**
 * Render a stored body_text as paragraphs, converting ``*…*`` spans to bold.
 * Used only when the procedure has no ``body_html`` snapshot (pre-feature or
 * pasted-text procedures). [EDGE D2]
 *
 * Returns an array of <p> elements (one per non-empty line).
 */
function fallbackParagraphs(bodyText) {
  return (bodyText || '')
    .split(/\n+/)
    .filter((line) => line.trim().length > 0)
    .map((line, i) => {
      // *bold* spans → <strong>; a lone asterisk stays literal.
      const parts = [];
      const regex = /\*([^*]+)\*/g;
      let last = 0;
      let match;
      while ((match = regex.exec(line)) !== null) {
        if (match.index > last) parts.push(line.slice(last, match.index));
        parts.push(<strong key={i + '-' + last}>{match[1]}</strong>);
        last = match.index + match[0].length;
      }
      if (last < line.length) parts.push(line.slice(last));
      return <p key={i}>{parts.length ? parts : line}</p>;
    });
}

export default function ProcedureViewPage() {
  const { procedureId } = useParams();
  const { initData, close } = useTelegram();

  const [proc, setProc] = useState(null);
  const [loadError, setLoadError] = useState(null); // {message, status}
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [quizStarted, setQuizStarted] = useState(false);
  const [quizError, setQuizError] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      const { data, error, status } = await getProcedure(procedureId, initData);
      if (!alive) return;
      if (error) {
        // Friendly status-specific screen, never the raw detail.
        if (status === 401) {
          setLoadError({ message: messages.PROC_ERR_AUTH, status });
        } else if (status === 404) {
          setLoadError({ message: messages.PROC_ERR_UNAVAILABLE, status });
        } else {
          setLoadError({ message: error, status });
        }
      } else {
        setProc(data);
      }
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, [procedureId, initData]);

  async function handleStartQuiz() {
    if (starting || quizStarted) return; // [EDGE C2] ignore double-taps
    setStarting(true);
    setQuizError(null);
    const { error, status } = await startProcedureQuiz(procedureId, initData);
    if (error) {
      // 503 → bot unavailable; page stays open so a retry is safe. [EDGE I1]
      if (status === 503) {
        setQuizError(messages.PROC_ERR_BOT_DOWN);
      } else {
        setQuizError(error);
      }
      setStarting(false);
      return;
    }
    setQuizStarted(true);
    setStarting(false);
    // Close the WebApp — the quiz continues in the Telegram chat. The hook's
    // close() is a guarded no-op outside Telegram (one source for the SDK).
    try {
      close();
    } catch {
      /* no-op outside Telegram */
    }
  }

  // ── Render states ──────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="guard-layout">
        <div className="loading">{messages.LABEL_LOADING}</div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="guard-layout" dir="rtl">
        <div className="error-banner">{loadError.message}</div>
      </div>
    );
  }

  if (!proc) {
    return (
      <div className="guard-layout" dir="rtl">
        <div className="error-banner">{messages.PROC_ERR_UNAVAILABLE}</div>
      </div>
    );
  }

  return (
    <div className="guard-layout" dir="rtl">
      <h1 className="procedure-title">{proc.title}</h1>

      {proc.passed && (
        <span className="passed-badge">{messages.PROC_PASSED_BADGE}</span>
      )}

      {proc.body_html ? (
        // Sanitized server-side (nh3); this is the ONLY field ever injected.
        // [EDGE D5]
        <div
          className="procedure-body"
          dangerouslySetInnerHTML={{ __html: proc.body_html }}
        />
      ) : (
        <div className="procedure-body">{fallbackParagraphs(proc.body_text)}</div>
      )}

      {quizError && <div className="error-banner">{quizError}</div>}

      {proc.quiz_open === false ? (
        // Availability window closed: only the quiz is blocked — the reading
        // above stays. [quiz_availability_window EDGE U1]
        <div className="quiz-sent">{messages.PROC_QUIZ_CLOSED}</div>
      ) : quizStarted ? (
        <div className="quiz-sent">{messages.PROC_QUIZ_SENT}</div>
      ) : (
        <button
          type="button"
          className="submit-btn"
          onClick={handleStartQuiz}
          disabled={starting}
        >
          {starting ? messages.PROC_QUIZ_SENDING : messages.PROC_QUIZ_BTN}
        </button>
      )}
    </div>
  );
}
