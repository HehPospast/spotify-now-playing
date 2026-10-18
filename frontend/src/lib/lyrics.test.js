import test from 'node:test';
import assert from 'node:assert/strict';
import { findActiveLyric, normalizeLyrics, parseLrc, syllableProgress } from './lyrics.js';

const payload = (lines, extra = {}) => ({ track_id: 'track-a', sync_type: 'line', lines, ...extra });

test('background vocals retain independent syllable intervals and do not truncate lead', () => {
  const lyrics = normalizeLyrics(payload([
    { start_ms: 1000, end_ms: 3000, text: 'Lead', syllables: [{ text: 'Lead', start_ms: 1000, end_ms: 3000 }],
      background: [{ start_ms: 1500, end_ms: 3500, text: 'Backing', syllables: [{ text: 'Backing', start_ms: 1500, end_ms: 3500 }] }] }
  ], { sync_type: 'syllable' }), 'track-a', 5000);
  assert.equal(lyrics.lines[0].syllables[0].end_ms, 3000);
  assert.equal(lyrics.lines[0].background[0].syllables[0].end_ms, 3500);
  assert.equal(syllableProgress(lyrics.lines[0].background[0].syllables[0], 2500), 0.5);
});

test('LRC and contract offsets are added once', () => {
  const lyrics = normalizeLyrics({ track_id: 'track-a', offset_ms: 200, lrc: '[offset:300]\n[00:01.000]Synthetic' }, 'track-a', 5000);
  assert.equal(lyrics.offset_ms, 500);
  assert.equal(findActiveLyric(lyrics.lines, 1499, lyrics.offset_ms), -1);
  assert.equal(findActiveLyric(lyrics.lines, 1500, lyrics.offset_ms), 0);
});

test('absent or stale-track lyrics never appear on the current track', () => {
  assert.equal(normalizeLyrics(null, 'track-a').status, 'unavailable');
  assert.equal(normalizeLyrics(payload([{ start_ms: 0, text: 'old' }]), 'track-b').status, 'unavailable');
});

test('normalize timing order, filter malformed entries, and clamp at next line and track end', () => {
  const normalized = normalizeLyrics(payload([
    { start_ms: 3000, end_ms: 9000, text: ' second ' },
    { start_ms: 1000, end_ms: 5000, text: 'first' },
    { start_ms: -1, text: 'bad' },
    { start_ms: 5000, text: 'past track end' },
    { start_ms: null, text: 'bad' },
    { start_ms: 3500, end_ms: 3400, text: 'reversed interval' },
    { start_ms: 2000, text: 123 }
  ]), 'track-a', 5000);
  assert.deepEqual(normalized.lines, [
    { start_ms: 1000, end_ms: 3000, text: 'first' },
    { start_ms: 3000, end_ms: 5000, text: ' second ' }
  ]);
});

test('timeline handles exact boundaries, instrumental gaps, and seeks backwards', () => {
  const { lines } = normalizeLyrics(payload([
    { start_ms: 1000, end_ms: 2000, text: 'first' },
    { start_ms: 3000, text: 'second' }
  ]), 'track-a', 5000);
  assert.equal(findActiveLyric(lines, 999), -1);
  assert.equal(findActiveLyric(lines, 1000), 0);
  assert.equal(findActiveLyric(lines, 2000), -1);
  assert.equal(findActiveLyric(lines, 3000), 1);
  assert.equal(findActiveLyric(lines, 5000), -1);
  assert.equal(findActiveLyric(lines, 1500), 0);
});

test('positive offset delays lyrics rather than advancing them', () => {
  const { lines, offset_ms } = normalizeLyrics(payload([{ start_ms: 1000, text: 'line' }], { offset_ms: 200 }), 'track-a', 5000);
  assert.equal(findActiveLyric(lines, 1199, offset_ms), -1);
  assert.equal(findActiveLyric(lines, 1200, offset_ms), 0);
});

test('simultaneous vocals merge into one row with a valid duration', () => {
  const { lines } = normalizeLyrics(payload([
    { start_ms: 0, end_ms: 1000, text: 'lead' },
    { start_ms: 0, end_ms: 2000, text: 'backing' },
    { start_ms: 3000, text: 'next' }
  ]), 'track-a', 5000);
  assert.deepEqual(lines[0], { start_ms: 0, end_ms: 2000, text: 'lead / backing' });
});

test('static lyrics remain untimed and attribution cannot execute javascript', () => {
  const normalized = normalizeLyrics(payload([{ text: '<script>plain text</script>' }], {
    sync_type: 'none',
    source: { name: 'Provider', url: 'javascript:alert(1)' },
    credits: [{ name: 'unsafe', url: 'data:text/html,unsafe' }, { name: 'Maker', url: 'https://example.com/maker' }]
  }), 'track-a');
  assert.equal(normalized.status, 'unsynced');
  assert.equal(normalized.lines[0].text, '<script>plain text</script>');
  assert.equal(normalized.source.url, null);
  assert.deepEqual(normalized.credits, [{ name: 'Maker', url: 'https://example.com/maker' }]);
});

test('loading and error states carry no stale lines', () => {
  assert.equal(normalizeLyrics(payload([], { status: 'loading' }), 'track-a').status, 'loading');
  assert.equal(normalizeLyrics(payload([], { status: 'error' }), 'track-a').status, 'error');
  assert.deepEqual(normalizeLyrics(payload([], { sync_type: 'invalid' }), 'track-a').lines, []);
});

test('missing provider is explicitly attributed as unknown and provenance marks survive', () => {
  const text = '\uFEFFlyric\u200B';
  const normalized = normalizeLyrics(payload([{ start_ms: 0, text }]), 'track-a', 1000);
  assert.equal(normalized.source.name, 'source unknown');
  assert.equal(normalized.lines[0].text, text);
});

test('LRC expands repeated timestamps and parses seconds, hundredths and milliseconds', () => {
  const { lines, offset_ms } = parseLrc('[ti:Title]\r\n[ar:Artist]\r\n[00:01.5][00:03.050]repeated\r\n[01:02]minute\r\n[offset:+250]');
  assert.equal(offset_ms, 250);
  assert.deepEqual(lines, [
    { start_ms: 1500, text: 'repeated' },
    { start_ms: 3050, text: 'repeated' },
    { start_ms: 62000, text: 'minute' }
  ]);
});

test('LRC normalizes unsorted timing, empty instrumental rows and signed offset against playback', () => {
  const lyrics = normalizeLyrics({ track_id: 'track-a', lrc: '[offset:-200]\n[00:04.00]later\n[00:02.50]\n[00:01.00]first' }, 'track-a', 6000);
  assert.equal(lyrics.status, 'ready');
  assert.equal(findActiveLyric(lyrics.lines, 799, lyrics.offset_ms), -1);
  assert.equal(findActiveLyric(lyrics.lines, 800, lyrics.offset_ms), 0);
  assert.equal(lyrics.lines[findActiveLyric(lyrics.lines, 2300, lyrics.offset_ms)].text, '');
  assert.equal(findActiveLyric(lyrics.lines, 3800, lyrics.offset_ms), 2);
});

test('LRC plain text has no fabricated timing and malformed tags are not displayed', () => {
  const lyrics = normalizeLyrics({ track_id: 'track-a', lrc: '[ti:Title]\n[00:99.00]invalid\nfirst\nsecond' }, 'track-a');
  assert.equal(lyrics.status, 'unsynced');
  assert.deepEqual(lyrics.lines.map(line => line.text), ['first', 'second']);
});

test('enhanced LRC displays clean line text while preserving provider marks', () => {
  const { lines } = parseLrc('\uFEFF[00:01.00]<00:01.00>Hello <00:01.50>world\u200B');
  assert.equal(lines[0].text, 'Hello world\u200B');
  assert.deepEqual(lines[0].syllables, [
    { text: 'Hello ', start_ms: 1000, end_ms: 1500 },
    { text: 'world\u200B', start_ms: 1500 }
  ]);
});

test('enhanced LRC preserves syllable timing and fills only the sung portion', () => {
  const lyrics = normalizeLyrics({ track_id: 'track-a', lrc: '[00:01.00]<00:01.00>Hel<00:01.50>lo <00:02.00>world<00:03.00>\n[00:04.00]next' }, 'track-a', 6000);
  assert.equal(lyrics.status, 'ready');
  const syllables = lyrics.lines[0].syllables;
  assert.equal(syllableProgress(syllables[0], 999), 0);
  assert.equal(syllableProgress(syllables[0], 1250), 0.5);
  assert.equal(syllableProgress(syllables[0], 1600), 1);
  assert.equal(syllableProgress(syllables[1], 1600), 0.2);
  assert.equal(syllableProgress(syllables[2], 1600), 0);
  assert.equal(syllableProgress(syllables[0], 1450, 200), 0.5);
});

test('malformed syllables fall back to line timing without losing text', () => {
  const lyrics = normalizeLyrics(payload([{ start_ms: 0, end_ms: 3000, text: 'hello', syllables: [{ text: 'other', start_ms: 0, end_ms: 2000 }] }], { sync_type: 'syllable' }), 'track-a', 5000);
  assert.equal(lyrics.lines[0].text, 'hello');
  assert.equal(lyrics.lines[0].syllables, undefined);
});
