// Admin navbar — brand wordmark + nav links + logout.
const { Button: KitButton_nav } = window.IlutsimDesignSystem_f4254f;

function KitNavbar({ current, onNavigate }) {
  const links = [
    { id: 'guards', label: 'מאבטחים' },
    { id: 'weeks', label: 'שבועות' },
    { id: 'submissions', label: 'דיווחים' },
    { id: 'events', label: 'אירועים' },
    { id: 'export', label: 'ייצוא' },
    { id: 'settings', label: 'הגדרות' },
  ];
  return (
    <nav className="navbar">
      <div className="navbar-brand">ניהול מערכת אילוצים</div>
      <div className="navbar-links">
        {links.map((l) => (
          <a key={l.id} className={current === l.id ? 'active' : ''} onClick={() => onNavigate(l.id)}>
            {l.label}
          </a>
        ))}
        <KitButton_nav variant="secondary" size="sm" onClick={() => onNavigate('login')}>התנתק</KitButton_nav>
      </div>
    </nav>
  );
}
window.KitNavbar = KitNavbar;
