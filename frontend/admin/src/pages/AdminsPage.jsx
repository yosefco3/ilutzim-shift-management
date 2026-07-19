import AdminsSection from '../components/AdminsSection';
import messages from '../utils/messages';

const t = messages.settings.admins;

// Dedicated admins-management page — SUPER_ADMIN only. The navbar link and the
// route are role-gated in the UI; the backend enforces 403 for everyone else.
export default function AdminsPage() {
  return (
    <div className="page">
      <h2>{t.title}</h2>
      <p className="page-subtitle text-muted">{t.subtitle}</p>
      <AdminsSection />
    </div>
  );
}
