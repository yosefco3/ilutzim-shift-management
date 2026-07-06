/**
 * Banner shown when the week is not open for submissions.
 * Displays a status-specific message.
 */
import { messages } from "../../utils/guardMessages.js";

// 3-state model: closed (reopenable) / locked (final). No 'published'.
const STATUS_MESSAGES = {
  closed: messages.LOCK_STATUS_CLOSED,
  locked: messages.LOCK_STATUS_LOCKED,
};

export default function LockBanner({ status }) {
  const text = STATUS_MESSAGES[status] || messages.LOCK_NO_WEEK;
  return <div className="lock-banner">{text}</div>;
}