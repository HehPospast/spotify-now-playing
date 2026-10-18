import { memo, useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { useIsPresent, useReducedMotion } from 'framer-motion';
import { findActiveLyric, syllableProgress } from '../lib/lyrics';

const IDLE_RETURN_MS = 5000;
const TRANSFER_MS = 260;
const SCROLL_MS = 500;
const ease = (t) => t * t * (3 - 2 * t);

const LyricText = memo(function LyricText({ line, progress, offset }) {
  const words = useMemo(() => {
    const groups = [];
    let word = [];
    (line.syllables || []).forEach((syllable, index, syllables) => {
      word.push(syllable);
      if (/\s$/.test(syllable.text) || /^\s/.test(syllables[index + 1]?.text || '') || index === syllables.length - 1) {
        groups.push(word);
        word = [];
      }
    });
    return groups;
  }, [line.syllables]);
  if (!words.length) return <span className="spotify-lyric-text">{line.text || '♪'}</span>;
  return (
    <span className="spotify-lyric-text">
      {words.map((word, wordIndex) => (
        <span className="spotify-lyric-word" key={wordIndex}>
          {word.map((syllable, index) => (
            <span
              className="spotify-lyric-syllable"
              key={`${syllable.start_ms}-${index}`}
              style={{ '--spotify-syllable-progress': `${syllableProgress(syllable, progress, offset) * 100}%` }}
            >{syllable.text}</span>
          ))}
        </span>
      ))}
    </span>
  );
});

function SpotifyLyrics({ lyrics, progress }) {
  const isPresent = useIsPresent();
  const synced = lyrics.status === 'ready';
  const activeIndex = synced ? findActiveLyric(lyrics.lines, progress, lyrics.offset_ms) : -1;
  const [highlightedIndex, setHighlightedIndex] = useState(activeIndex);
  const [manual, setManual] = useState(false);
  const reducedMotion = useReducedMotion();
  const viewportRef = useRef(null);
  const listRef = useRef(null);
  const markerRef = useRef(null);
  const rowRefs = useRef([]);
  const frameRef = useRef(null);
  const fadeRef = useRef(null);
  const idleRef = useRef(null);
  const touchRef = useRef(false);
  const manualRef = useRef(false);
  const previousRef = useRef(null);
  const currentRef = useRef({ activeIndex, reducedMotion, synced });
  const returnRef = useRef(null);
  const viewportId = useId();
  currentRef.current = { activeIndex, reducedMotion, synced };

  const stopMotion = useCallback(() => {
    cancelAnimationFrame(frameRef.current);
    frameRef.current = null;
    fadeRef.current?.cancel();
    fadeRef.current = null;
  }, []);

  const placeMarker = useCallback((index = currentRef.current.activeIndex) => {
    const marker = markerRef.current;
    const row = rowRefs.current[index];
    const viewport = viewportRef.current;
    if (!marker || !viewport) return;
    marker.hidden = !row || !currentRef.current.synced;
    if (row) {
      marker.style.top = `${row.offsetTop - viewport.scrollTop}px`;
      marker.style.height = `${row.offsetHeight}px`;
    }
  }, []);

  const followLine = useCallback((index, returning = false, immediate = false) => {
    const viewport = viewportRef.current;
    const row = rowRefs.current[index];
    const marker = markerRef.current;
    if (!viewport || !marker) return;
    stopMotion();
    if (!row) {
      setHighlightedIndex(-1);
      placeMarker(-1);
      return;
    }

    const from = viewport.scrollTop;
    const to = Math.max(0, Math.min(
      row.offsetTop + row.offsetHeight / 2 - viewport.clientHeight / 2,
      viewport.scrollHeight - viewport.clientHeight
    ));
    const previous = previousRef.current;
    const adjacent = previous !== null && Math.abs(index - previous) === 1;
    const transfer = !returning && adjacent && !immediate && !currentRef.current.reducedMotion;
    const markerFrom = parseFloat(marker.style.top) || 0;
    const heightFrom = parseFloat(marker.style.height) || row.offsetHeight;
    const markerTo = row.offsetTop - from;
    previousRef.current = index;

    if (immediate || currentRef.current.reducedMotion) {
      viewport.scrollTop = to;
      setHighlightedIndex(index);
      placeMarker(index);
      return;
    }

    // A seek across several verses should not race the whole text past the reader.
    if (!returning && !adjacent) {
      viewport.scrollTop = to;
      setHighlightedIndex(index);
      placeMarker(index);
      fadeRef.current = listRef.current?.animate(
        [{ opacity: 0.35 }, { opacity: 1 }], { duration: 260, easing: 'ease-out' }
      );
      return;
    }

    const delay = transfer ? TRANSFER_MS : 0;
    const duration = returning ? 760 : SCROLL_MS;
    const start = performance.now();
    let transferred = !transfer;
    marker.hidden = false;
    if (!transfer) setHighlightedIndex(index);

    const step = (now) => {
      const elapsed = now - start;
      if (elapsed < delay) {
        const t = ease(elapsed / delay);
        marker.style.top = `${markerFrom + (markerTo - markerFrom) * t}px`;
        marker.style.height = `${heightFrom + (row.offsetHeight - heightFrom) * t}px`;
      } else {
        if (!transferred) {
          transferred = true;
          setHighlightedIndex(index);
        }
        const t = Math.min(1, (elapsed - delay) / duration);
        viewport.scrollTop = from + (to - from) * ease(t);
        placeMarker(index);
        if (t === 1) {
          frameRef.current = null;
          return;
        }
      }
      frameRef.current = requestAnimationFrame(step);
    };
    frameRef.current = requestAnimationFrame(step);
  }, [placeMarker, stopMotion]);

  const scheduleReturn = useCallback(() => {
    clearTimeout(idleRef.current);
    if (manualRef.current && !touchRef.current && currentRef.current.synced) {
      idleRef.current = window.setTimeout(() => returnRef.current?.(), IDLE_RETURN_MS);
    }
  }, []);

  const returnToCurrent = useCallback(() => {
    clearTimeout(idleRef.current);
    if (touchRef.current) return;
    manualRef.current = false;
    setManual(false);
    followLine(currentRef.current.activeIndex, true);
  }, [followLine]);
  returnRef.current = returnToCurrent;

  const pauseFollow = useCallback(() => {
    if (!currentRef.current.synced) return;
    stopMotion();
    manualRef.current = true;
    setManual(true);
    setHighlightedIndex(currentRef.current.activeIndex);
    placeMarker();
    scheduleReturn();
  }, [placeMarker, scheduleReturn, stopMotion]);

  useEffect(() => {
    if (manualRef.current) {
      setHighlightedIndex(activeIndex);
      previousRef.current = activeIndex;
      placeMarker();
    } else if (previousRef.current !== activeIndex) {
      followLine(activeIndex, false, previousRef.current === null);
    }
  }, [activeIndex, followLine, placeMarker]);

  useEffect(() => {
    const viewport = viewportRef.current;
    const list = listRef.current;
    if (!viewport || !list) return undefined;
    const resize = () => {
      if (manualRef.current) placeMarker();
      else if (frameRef.current === null) followLine(currentRef.current.activeIndex, false, true);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(viewport);
    observer.observe(list);
    return () => observer.disconnect();
  }, [lyrics.lines, followLine, placeMarker]);

  useEffect(() => () => {
    stopMotion();
    clearTimeout(idleRef.current);
  }, [stopMotion]);

  const message = {
    loading: 'loading lyrics…',
    error: 'lyrics are temporarily unavailable',
    unavailable: 'lyrics unavailable for this track'
  }[lyrics.status];

  return (
    <div className="spotify-lyrics" aria-hidden={!isPresent || undefined} inert={!isPresent ? '' : undefined}>
      {manual && synced && (
        <button className="spotify-lyrics-return" type="button" onClick={returnToCurrent} aria-controls={viewportId}>↳ к текущей строке</button>
      )}
      {message ? <div className="spotify-lyrics-message" role="status">{message}</div> : (
        <div className={`spotify-lyrics-window ${synced ? '' : 'is-unsynced'}`}>
          <div className="spotify-lyrics-marker" ref={markerRef} hidden />
          <div
            id={viewportId}
            className="spotify-lyrics-scroll"
            ref={viewportRef}
            tabIndex={0}
            role="region"
            aria-label="Текст песни"
            onWheel={pauseFollow}
            onTouchStart={() => { touchRef.current = true; pauseFollow(); }}
            onTouchMove={pauseFollow}
            onTouchEnd={() => { touchRef.current = false; scheduleReturn(); }}
            onTouchCancel={() => { touchRef.current = false; scheduleReturn(); }}
            onKeyDown={(event) => {
              if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key)) pauseFollow();
            }}
            onScroll={() => {
              if (manualRef.current) { placeMarker(); scheduleReturn(); }
              else if (frameRef.current === null) placeMarker();
            }}
          >
            <div className="spotify-lyrics-list" ref={listRef}>
              {lyrics.lines.map((line, index) => (
                <div
                  key={`${line.start_ms ?? 'text'}-${index}`}
                  ref={(node) => { rowRefs.current[index] = node; }}
                  className={`spotify-lyric-row ${index === highlightedIndex && synced ? 'is-current' : ''}`}
                  aria-current={synced && index === activeIndex ? 'true' : undefined}
                >
                  <span className="spotify-lyric-number" aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
                  <div>
                    <LyricText line={line} progress={progress} offset={lyrics.offset_ms} />
                    {line.background?.map((group, groupIndex) => (
                      <div className="spotify-lyric-background" key={groupIndex}>
                        <LyricText line={group} progress={progress} offset={lyrics.offset_ms} />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
      {lyrics.source && (
        <div className="spotify-lyrics-attribution">
          {lyrics.source.url ? <a href={lyrics.source.url} target="_blank" rel="noreferrer">{lyrics.source.name}</a> : <span>{lyrics.source.name}</span>}
          {lyrics.credits.map((credit) => <a key={`${credit.name}-${credit.url}`} href={credit.url} target="_blank" rel="noreferrer">{credit.name}</a>)}
        </div>
      )}
    </div>
  );
}

export default SpotifyLyrics;
