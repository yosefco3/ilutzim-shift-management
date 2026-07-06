// Admin login — centered card with indigo radial glow behind it.
const { Card: KitCard_l, Button: KitBtn_l, Field: KitField_l, TextInput: KitInput_l, Alert: KitAlert_l } = window.IlutsimDesignSystem_f4254f;

function LoginScreen({ onLogin }) {
  const [username, setUsername] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [error, setError] = React.useState('');

  const submit = () => {
    if (!username || !password) { setError('שם משתמש או סיסמה שגויים'); return; }
    setError('');
    onLogin && onLogin();
  };

  return (
    <div className="login-page">
      <KitCard_l className="login-card" style={{ padding: '2.5rem' }}>
        <h2>כניסת מנהל</h2>
        {error && <div style={{ marginBottom: '1rem' }}><KitAlert_l tone="error">{error}</KitAlert_l></div>}
        <KitField_l label="שם משתמש"><KitInput_l value={username} onChange={(e) => setUsername(e.target.value)} /></KitField_l>
        <KitField_l label="סיסמה"><KitInput_l type="password" value={password} onChange={(e) => setPassword(e.target.value)} /></KitField_l>
        <div style={{ marginTop: '0.5rem' }}>
          <KitBtn_l variant="primary" block onClick={submit}>התחבר</KitBtn_l>
        </div>
      </KitCard_l>
    </div>
  );
}
window.LoginScreen = LoginScreen;
