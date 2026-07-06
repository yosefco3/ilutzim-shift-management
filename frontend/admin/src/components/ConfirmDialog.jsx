import messages from '../utils/messages';

export default function ConfirmDialog({
  open = true,
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
}) {
  if (!open) return null;

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        {title && <h3 className="modal-title">{title}</h3>}
        <p>{message}</p>
        <div className="modal-actions">
          <button className="btn btn-danger" onClick={onConfirm}>
            {confirmLabel || messages.common.confirm}
          </button>
          <button className="btn btn-secondary" onClick={onCancel}>
            {messages.common.cancel}
          </button>
        </div>
      </div>
    </div>
  );
}
