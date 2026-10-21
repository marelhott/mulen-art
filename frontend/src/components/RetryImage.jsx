import React, { useEffect, useState } from "react";
import { retryUrl, RETRY_DELAYS_MS } from "../studioTools";

// An <img> that recovers from a failed load (a worker output that is not visible to the gateway yet,
// a busy server): it retries with a cache-busting URL, then falls back to `fallbackSrc` if given.
export function RetryImage({ src, fallbackSrc, ...props }) {
  const [attempt, setAttempt] = useState(0);
  const [useFallback, setUseFallback] = useState(false);
  useEffect(() => {
    setAttempt(0);
    setUseFallback(false);
  }, [src]);
  function onError() {
    if (attempt < RETRY_DELAYS_MS.length) {
      window.setTimeout(() => setAttempt((current) => current + 1), RETRY_DELAYS_MS[attempt]);
    } else if (fallbackSrc && !useFallback) {
      setUseFallback(true);
      setAttempt(0);
    }
  }
  const current = useFallback ? fallbackSrc : src;
  return <img {...props} src={retryUrl(current, attempt)} onError={onError} />;
}
