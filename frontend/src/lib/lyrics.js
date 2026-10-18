// Public playback/SSE contract. Provider-specific formats are adapted on the server.
// Positive offset_ms delays lyrics relative to Spotify progress_ms.
const unavailable = () => ({ status: 'unavailable', lines: [], offset_ms: 0, source: null, credits: [] });

const safeLink = (value) => {
  if (typeof value !== 'string') return null;
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
};

export function parseLrc(content) {
  const timed = [];
  const plain = [];
  let offset = 0;
  const rows = content.split(/\r\n|\n|\r/);
  const timestamp = /^[ \t]*\[(\d+):([0-5]\d)(?:[.:](\d{1,3}))?\]/;
  const wordTimestamp = /<(\d+):([0-5]\d)(?:[.:](\d{1,3}))?>/g;
  const toMilliseconds = (match) => Number(match[1]) * 60000 + Number(match[2]) * 1000 + Number((match[3] || '').padEnd(3, '0'));

  rows.forEach((rawRow, rowIndex) => {
    // Encoding BOM before the first tag is not lyric text. Never strip marks from the text itself.
    const row = rowIndex === 0 ? rawRow.replace(/^\uFEFF(?=\[)/, '') : rawRow;
    const metadata = row.match(/^[ \t]*\[offset:([+-]?\d+)\][ \t]*$/i);
    if (metadata) { offset = Number(metadata[1]); return; }
    if (/^[ \t]*(?:\[[a-z][\w-]*:[^\]]*\][ \t]*)+$/i.test(row)) return;

    const starts = [];
    let cursor = 0;
    let match;
    while ((match = row.slice(cursor).match(timestamp))) {
      starts.push(toMilliseconds(match));
      cursor += match[0].length;
    }
    if (starts.length) {
      const body = row.slice(cursor);
      const text = body.replace(wordTimestamp, '');
      const markers = [...body.matchAll(wordTimestamp)];
      const syllables = [];
      if (markers.length && markers[0].index > 0) {
        syllables.push({ text: body.slice(0, markers[0].index), start_ms: starts[0], end_ms: toMilliseconds(markers[0]) });
      }
      markers.forEach((marker, index) => {
        const segment = body.slice(marker.index + marker[0].length, markers[index + 1]?.index ?? body.length);
        if (segment) syllables.push({
          text: segment,
          start_ms: toMilliseconds(marker),
          ...(markers[index + 1] ? { end_ms: toMilliseconds(markers[index + 1]) } : {})
        });
      });
      starts.forEach((start_ms) => {
        const delta = start_ms - starts[0];
        timed.push({ start_ms, text, ...(syllables.length ? { syllables: syllables.map(syllable => ({
          ...syllable, start_ms: syllable.start_ms + delta,
          ...(syllable.end_ms !== undefined ? { end_ms: syllable.end_ms + delta } : {})
        })) } : {}) });
      });
    } else if (row.trim() && !/^[ \t]*\[/.test(row)) {
      plain.push({ text: row });
    }
  });
  return {
    sync_type: timed.length ? timed.some(line => line.syllables?.length) ? 'syllable' : 'line' : 'none',
    lines: timed.length ? timed : plain,
    offset_ms: Number.isFinite(offset) ? offset : 0
  };
}

export function normalizeLyrics(raw, trackId, durationMs = 0) {
  if (!raw || !trackId || raw.track_id !== trackId) return unavailable();
  if (['loading', 'error', 'unavailable'].includes(raw.status)) {
    return { ...unavailable(), status: raw.status };
  }
  if (typeof raw.lrc === 'string') {
    const parsed = parseLrc(raw.lrc);
    raw = {
      ...raw,
      ...parsed,
      offset_ms: parsed.offset_ms + (Number.isFinite(raw.offset_ms) ? raw.offset_ms : 0)
    };
  }
  if (!Array.isArray(raw.lines) || !['line', 'syllable', 'none'].includes(raw.sync_type)) return unavailable();

  const duration = Number.isFinite(durationMs) && durationMs > 0 ? durationMs : Infinity;
  const lines = raw.lines
    .filter((line) => line && typeof line.text === 'string')
    .filter((line) => raw.sync_type === 'none' || (
      Number.isFinite(line.start_ms) && line.start_ms >= 0 && line.start_ms < duration &&
      (line.end_ms == null || (Number.isFinite(line.end_ms) && line.end_ms > line.start_ms))
    ))
    // Keep provider text intact, including invisible provenance marks.
    .map((line) => ({ text: line.text, start_ms: line.start_ms, end_ms: line.end_ms,
      ...(Array.isArray(line.syllables) ? { syllables: line.syllables } : {}),
      ...(Array.isArray(line.background) ? { background: line.background } : {}) }));
  if (!lines.length) return unavailable();

  if (raw.sync_type !== 'none') {
    lines.sort((a, b) => a.start_ms - b.start_ms);
    // Simultaneous vocals belong to one display row rather than a zero-length row.
    for (let index = lines.length - 1; index > 0; index -= 1) {
      if (lines[index].start_ms === lines[index - 1].start_ms) {
        lines[index - 1].text = [lines[index - 1].text, lines[index].text].filter(Boolean).join(' / ');
        delete lines[index - 1].syllables;
        const background = [...(lines[index - 1].background || []), ...(lines[index].background || [])];
        if (background.length) lines[index - 1].background = background;
        const ends = [lines[index - 1].end_ms, lines[index].end_ms].filter(Number.isFinite);
        lines[index - 1].end_ms = ends.length ? Math.max(...ends) : undefined;
        lines.splice(index, 1);
      }
    }
    lines.forEach((line, index) => {
      line.end_ms = Math.min(line.end_ms ?? Infinity, lines[index + 1]?.start_ms ?? duration, duration);
      if (line.syllables) {
        const syllables = line.syllables
          .filter(syllable => syllable && typeof syllable.text === 'string' && Number.isFinite(syllable.start_ms) && syllable.start_ms >= line.start_ms && syllable.start_ms < line.end_ms)
          .map(syllable => ({ text: syllable.text, start_ms: syllable.start_ms, end_ms: syllable.end_ms }))
          .sort((a, b) => a.start_ms - b.start_ms);
        syllables.forEach((syllable, syllableIndex) => {
          syllable.end_ms = Math.min(syllable.end_ms ?? Infinity, syllables[syllableIndex + 1]?.start_ms ?? line.end_ms, line.end_ms);
        });
        if (syllables.length && syllables.every(syllable => Number.isFinite(syllable.end_ms) && syllable.end_ms > syllable.start_ms) && syllables.map(syllable => syllable.text).join('') === line.text) line.syllables = syllables;
        else delete line.syllables;
      }
    });
  }

  // Background phrases have their own intervals and can overlap the lead/next row.
  // Normalize them separately so they cannot truncate the lead's exact timings.
  lines.forEach(line => {
    if (!line.background) return;
    line.background = line.background.flatMap(group => {
      const normalized = normalizeLyrics({ ...raw, lrc: undefined, lines: [{ ...group, background: undefined }] }, trackId, durationMs);
      return normalized.lines;
    });
  });

  const source = typeof raw.source?.name === 'string'
    ? { name: raw.source.name, url: safeLink(raw.source.url) }
    : { name: 'source unknown', url: null };
  const credits = Array.isArray(raw.credits) ? raw.credits
    .filter((credit) => typeof credit?.name === 'string' && safeLink(credit.url))
    .map((credit) => ({ name: credit.name, url: safeLink(credit.url) })) : [];

  return {
    status: raw.sync_type === 'none' ? 'unsynced' : 'ready',
    lines,
    offset_ms: Number.isFinite(raw.offset_ms) ? raw.offset_ms : 0,
    source,
    credits
  };
}

export function syllableProgress(syllable, progressMs, offsetMs = 0) {
  const duration = syllable.end_ms - syllable.start_ms;
  if (!Number.isFinite(duration) || duration <= 0) return 0;
  return Math.min(1, Math.max(0, (progressMs - offsetMs - syllable.start_ms) / duration));
}

export function findActiveLyric(lines, progressMs, offsetMs = 0) {
  const time = progressMs - offsetMs;
  let left = 0;
  let right = lines.length - 1;
  let active = -1;
  while (left <= right) {
    const middle = Math.floor((left + right) / 2);
    if (lines[middle].start_ms <= time) {
      active = middle;
      left = middle + 1;
    } else {
      right = middle - 1;
    }
  }
  return active >= 0 && time < lines[active].end_ms ? active : -1;
}
