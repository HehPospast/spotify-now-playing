import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { useEffect, useId, useMemo, useState } from 'react';
import spotifyIcon from '../assets/spotify.svg';
import { normalizeLyrics } from '../lib/lyrics';
import { mergePlayback, normalizePlayback, playbackProgress } from '../lib/playback';
import SpotifyLyrics from './SpotifyLyrics';

const CURRENTLY_PLAYING_URL = '/api/v1/spotify/public/currently-playing';
const STREAM_URL = '/api/v1/spotify/public/stream';

const formatTime = (milliseconds = 0) => {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = String(totalSeconds % 60).padStart(2, '0');
  return `${minutes}:${seconds}`;
};

function SpotifyTerminalPlayer() {
  const [playback, setPlayback] = useState(null);
  const [connection, setConnection] = useState('connecting');
  const [lyricsOpen, setLyricsOpen] = useState(true);
  const [coverAvailable, setCoverAvailable] = useState(true);
  const [now, setNow] = useState(Date.now());
  const reducedMotion = useReducedMotion();
  const lyricsId = useId();

  useEffect(() => {
    let active = true;
    let receivedStream = false;
    const controller = new AbortController();

    const applyPlayback = (payload, fromStream = false) => {
      const next = normalizePlayback(payload);
      if (!active) return;
      if (!next) { setConnection('reconnecting'); setPlayback(null); return; }
      if (!fromStream && receivedStream) return;
      if (fromStream) receivedStream = true;

      setPlayback((current) => mergePlayback(current, next));
      setConnection('live');
    };

    fetch(CURRENTLY_PLAYING_URL, {
      signal: controller.signal,
      headers: { Accept: 'application/json' }
    })
      .then((response) => {
        if (!response.ok) throw new Error(`Spotify API returned ${response.status}`);
        return response.json();
      })
      .then((payload) => applyPlayback(payload))
      .catch((error) => {
        if (active && error.name !== 'AbortError') setConnection('reconnecting');
      });

    const stream = new EventSource(STREAM_URL);

    stream.addEventListener('open', () => {
      if (active) setConnection('live');
    });

    stream.addEventListener('playing', (event) => {
      try {
        applyPlayback(JSON.parse(event.data), true);
      } catch {
        // Ignore a malformed event and keep the last valid playback state.
      }
    });

    stream.onerror = () => {
      if (active) { setConnection('reconnecting'); setPlayback((current) => current ? { ...current, progress_ms: playbackProgress(current, Date.now()), receivedAt: Date.now(), is_playing: false } : null); }
    };

    return () => {
      active = false;
      controller.abort();
      stream.close();
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    setCoverAvailable(true);
  }, [playback?.item?.id]);

  const progress = useMemo(() => playbackProgress(playback, now), [now, playback]);

  const item = playback?.item;
  const artists = item?.artists?.map((artist) => artist.name).filter(Boolean).join(', ');
  const duration = item?.duration_ms || 0;
  const progressPercent = duration ? (progress / duration) * 100 : 0;
  const coverUrl = item?.album?.image_url;
  const lyrics = useMemo(
    () => normalizeLyrics(playback?.lyrics, item?.id, duration),
    [playback?.lyrics, item?.id, duration]
  );
  const lyricsKey = useMemo(
    () => JSON.stringify([item?.id, lyrics.status, lyrics.lines, lyrics.offset_ms]),
    [item?.id, lyrics]
  );

  if (!playback && connection !== 'live') {
    return (
      <section className="spotify-terminal-player is-loading" aria-label="Spotify activity">
        <div className="spotify-terminal-heading">
          <span>[ spotify://activity ]</span>
          <span className="spotify-terminal-connection">○ connecting</span>
        </div>
        <div className="spotify-terminal-message">$ spotify status --watch</div>
        <div className="spotify-terminal-muted">waiting for public playback stream<span className="spotify-terminal-dots">...</span></div>
      </section>
    );
  }

  if (!item) {
    return (
      <section className="spotify-terminal-player is-idle" aria-label="Spotify activity">
        <div className="spotify-terminal-heading">
          <span>[ spotify://activity ]</span>
          <span className={`spotify-terminal-connection is-${connection}`}>
            {connection === 'live' ? '○ standby' : '◌ reconnecting'}
          </span>
        </div>
        <div className="spotify-terminal-message">♫ playback is quiet right now</div>
        <div className="spotify-terminal-muted">stream stays open - the next track will appear here automatically</div>
      </section>
    );
  }

  return (
    <section className="spotify-terminal-player is-playing" aria-label={`Now playing ${item.name} by ${artists}`}>
      <div className="spotify-terminal-heading">
        <span>[ spotify://now-playing ]</span>
        <span className={`spotify-terminal-connection is-${connection}`}>
          {connection === 'live' ? playback.is_playing ? '● live' : 'Ⅱ paused' : '◌ reconnecting'}
        </span>
      </div>

      <div className="spotify-terminal-track-row">
        <img className="spotify-terminal-icon" src={spotifyIcon} alt="Spotify" width="22" height="22" />
        <div className="spotify-terminal-track-copy">
          <a href={item.spotify_url} target="_blank" rel="noreferrer" className="spotify-terminal-track">
            {item.name}{item.explicit ? <span className="spotify-explicit" title="Explicit">E</span> : null}
          </a>
          <div className="spotify-terminal-artist">{artists || 'Unknown artist'}</div>
          {item.album?.name ? <div className="spotify-terminal-album">on {item.album.name}</div> : null}
        </div>
        {coverUrl && coverAvailable && (
          <a href={item.spotify_url} target="_blank" rel="noreferrer" className="spotify-terminal-mini-cover">
            <img src={coverUrl} width="48" height="48" alt={`Cover of ${item.album?.name || item.name}`} onError={() => setCoverAvailable(false)} />
          </a>
        )}
      </div>

      <AnimatePresence initial={false}>
        {lyricsOpen && (
          <motion.div
            id={lyricsId}
            className="spotify-lyrics-reveal"
            key="lyrics-panel"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: reducedMotion ? 0 : 0.36, ease: [0.22, 1, 0.36, 1] }}
          >
            <SpotifyLyrics key={lyricsKey} lyrics={lyrics} progress={progress} />
          </motion.div>
        )}
      </AnimatePresence>

      <div className="spotify-terminal-progress" aria-label={`${formatTime(progress)} of ${formatTime(duration)}`}>
        <div className="spotify-progress-rail" aria-hidden="true">
          <span style={{ width: `${progressPercent}%` }} />
        </div>
        <time>{formatTime(progress)}</time>
        <time>{formatTime(duration)}</time>
      </div>

      <div className="spotify-terminal-actions">
        <button type="button" onClick={() => setLyricsOpen((open) => !open)} aria-expanded={lyricsOpen} aria-controls={lyricsId}>
          {lyricsOpen ? '[-] hide lyrics' : '[+] show lyrics'}
        </button>
      </div>
    </section>
  );
}

export default SpotifyTerminalPlayer;
