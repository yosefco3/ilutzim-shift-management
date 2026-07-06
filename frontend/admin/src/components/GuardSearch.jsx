import messages from '../utils/messages';

// Search-by-name box shared by the guards, submissions and publish-preview
// pages. Purely presentational — the parent owns the query state and filtering.
export default function GuardSearch({ value, onChange }) {
  return (
    <input
      type="search"
      className="guard-search"
      value={value}
      placeholder={messages.common.searchGuard}
      aria-label={messages.common.searchGuard}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}
