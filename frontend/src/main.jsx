import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import SpotifyTerminalPlayer from './components/SpotifyTerminalPlayer';
import './style.css';

function Setup() {
  const [key, setKey] = useState('');
  const [message, setMessage] = useState(() => {
    const result = new URLSearchParams(location.search).get('spotify');
    if (result) history.replaceState(null, '', '/setup');
    return result === 'connected' ? 'Spotify connected. Your widget is ready.'
      : result === 'denied' ? 'Spotify access was cancelled. You can try again.' : '';
  });
  const embed = `<iframe src="${location.origin}/widget" title="Spotify now playing" width="100%" height="400" style="border:0" loading="lazy"></iframe>`;
  async function action(path, method = 'GET') {
    try {
      const response = await fetch(path, { method, headers: { 'X-Admin-Key': key } });
      if (!response.ok) throw new Error(response.status === 401 ? 'Check your owner key.' : 'Request failed. Try again.');
      const data = await response.json();
      setMessage(`${data.connected ? 'Spotify connected.' : 'Spotify disconnected.'}${data.telegram_enabled !== undefined ? ` Telegram: ${data.telegram_enabled ? 'enabled' : 'disabled'}. Lyrics: ${data.lyrics_enabled ? 'enabled' : 'disabled'}.` : ''}`);
    } catch (error) { setMessage(error.message); }
  }
  return <main className="setup">
    <a className="eyebrow" href="/widget">[ spotify://now-playing ]</a>
    <h1>Your music.<br/><span>Your little corner.</span></h1>
    <p>A Spotify widget and one Telegram message that follows your listening.</p>
    <form action="/auth/spotify" method="post">
      <label htmlFor="owner-key">Owner key <small>ADMIN_KEY from your .env</small></label>
      <input id="owner-key" name="admin_key" type="password" autoComplete="off" required value={key} onChange={event => setKey(event.target.value)} />
      <button className="primary" type="submit">Connect with Spotify ↗</button>
    </form>
    <div className="setup-actions">
      <button onClick={() => action('/api/admin/status')}>Check connection</button>
      <button onClick={() => action('/api/admin/disconnect', 'POST')}>Disconnect Spotify</button>
    </div>
    <p className="notice" role="status">{message}</p>
    <h2>Preview</h2><SpotifyTerminalPlayer />
    <h2>Embed anywhere</h2>
    <p>The widget is public. Anyone with its address can see your current track and available lyrics.</p>
    <pre><code>{embed}</code></pre>
    <p className="muted">Telegram and lyrics are optional. Configure them in .env and restart the app. Disconnect removes local Spotify tokens; revoke access from your Spotify account to remove the authorization itself.</p>
  </main>;
}

const setup = location.pathname === '/setup';
document.body.classList.toggle('widget-page', !setup);
document.documentElement.classList.toggle('widget-page', !setup);
createRoot(document.getElementById('root')).render(setup ? <Setup /> : <SpotifyTerminalPlayer />);
