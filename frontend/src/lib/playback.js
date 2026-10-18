export function normalizePlayback(payload, receivedAt = Date.now()) {
  if (!payload || payload.success !== true) return null;
  const observedAt = Date.parse(payload.updated_at);
  const elapsed = payload.is_playing && Number.isFinite(observedAt) ? Math.max(0, receivedAt - observedAt) : 0;
  return {
    ...payload,
    progress_ms: payload.item ? Math.min((Number(payload.progress_ms) || 0) + elapsed, payload.item.duration_ms || 0) : null,
    receivedAt
  };
}

export function mergePlayback(current, next) {
  if (current?.updated_at && next.updated_at && Date.parse(next.updated_at) < Date.parse(current.updated_at)) return current;
  return {
    ...next,
    lyrics: next.lyrics === undefined && next.item?.id && current?.item?.id === next.item.id
      ? current.lyrics : next.lyrics
  };
}

export function playbackProgress(playback, now) {
  if (!playback?.item) return 0;
  const elapsed = playback.is_playing ? Math.max(0, now - playback.receivedAt) : 0;
  return Math.min(Math.max((Number(playback.progress_ms) || 0) + elapsed, 0), playback.item.duration_ms || 0);
}
