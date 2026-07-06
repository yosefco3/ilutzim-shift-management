import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { login } from '../api/adminApiClient';
import messages from '../utils/messages';

export default function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(username, password);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err.message || messages.login.error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <form className="login-card card" onSubmit={handleSubmit}>
        <h2>{messages.login.title}</h2>
        {error && <div className="alert alert-error">{error}</div>}
        <div className="form-group">
          <label>{messages.login.username}</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} required />
        </div>
        <div className="form-group">
          <label>{messages.login.password}</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
          {loading ? messages.login.loading : messages.login.submit}
        </button>
      </form>
    </div>
  );
}