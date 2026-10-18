import test from 'node:test';
import assert from 'node:assert/strict';
import { mergePlayback, normalizePlayback, playbackProgress } from './playback.js';

const snapshot = (extra = {}) => ({ success: true, item: { id: 'a', duration_ms: 10000 }, progress_ms: 1000, is_playing: true, ...extra });

test('cached observations and network latency advance the playback clock once', () => {
  const playback = normalizePlayback(snapshot({ updated_at: '2026-10-14T00:00:00Z' }), Date.parse('2026-10-14T00:00:02Z'));
  assert.equal(playback.progress_ms, 3000);
  assert.equal(playbackProgress(playback, playback.receivedAt + 1000), 4000);
  assert.equal(playbackProgress(playback, playback.receivedAt + 20000), 10000);
});

test('pause freezes the clock and fresh SSE seeks correct it in either direction', () => {
  const paused = normalizePlayback(snapshot({ is_playing: false }), 100);
  assert.equal(playbackProgress(paused, 10000), 1000);
  const forward = mergePlayback(paused, normalizePlayback(snapshot({ progress_ms: 8000 }), 500));
  assert.equal(playbackProgress(forward, 600), 8100);
  const backward = mergePlayback(forward, normalizePlayback(snapshot({ progress_ms: 2000 }), 700));
  assert.equal(playbackProgress(backward, 800), 2100);
});

test('reconnection retains same-track lyrics and a track change clears them', () => {
  const current = normalizePlayback(snapshot({ lyrics: { track_id: 'a', status: 'ready' } }), 0);
  assert.equal(mergePlayback(current, normalizePlayback(snapshot(), 100)).lyrics, current.lyrics);
  assert.equal(mergePlayback(current, normalizePlayback(snapshot({ item: { id: 'b', duration_ms: 10000 } }), 100)).lyrics, undefined);
  assert.equal(mergePlayback(current, normalizePlayback(snapshot({ lyrics: { track_id: 'a', status: 'unavailable' } }), 100)).lyrics.status, 'unavailable');
});

test('older snapshots cannot roll playback back after an asynchronous lyrics frame', () => {
  const current = normalizePlayback(snapshot({ updated_at: '2026-10-14T00:00:02Z' }), 0);
  const stale = normalizePlayback(snapshot({ updated_at: '2026-10-14T00:00:01Z' }), 0);
  assert.equal(mergePlayback(current, stale), current);
  assert.equal(normalizePlayback({ success: false }), null);
});
