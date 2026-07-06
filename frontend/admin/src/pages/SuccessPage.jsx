/**
 * Success page shown after a guard submits their constraints.
 * Clean centered card replacing the inline success banner.
 */
import { messages } from "../utils/guardMessages.js";
import "../styles/guard.css";

export default function SuccessPage() {
  return (
    <div className="guard-layout success-page">
      <div className="success-card">
        <div className="success-icon">✅</div>
        <h2 className="success-title">{messages.SUCCESS_SUBMITTED}</h2>
        <a href="/submit" className="success-edit-btn">
          ✏️ ערוך אילוצים
        </a>
      </div>
    </div>
  );
}