import React from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import App from "./App.jsx";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);


// Media cache (thumbnails and images are immutable): see public/sw.js.
if ("serviceWorker" in navigator && import.meta.env.PROD) {
  const register = () => navigator.serviceWorker.register("/sw.js").catch(() => {});
  if (document.readyState === "complete") register();
  else window.addEventListener("load", register);
}

// An installed home-screen app is suspended rather than closed, so it keeps running the code it started with.
// When it comes back to the foreground, compare the running bundle with the published one and reload if they differ
// (never while a generation is being followed: those jobs would otherwise be re-attached from storage mid-run).
if (import.meta.env.PROD) {
  const running = [...document.scripts].map((script) => script.src).find((src) => /\/assets\/index-[\w-]+\.js/.test(src));
  let checking = false;
  document.addEventListener("visibilitychange", async () => {
    if (document.visibilityState !== "visible" || !running || checking) return;
    checking = true;
    try {
      const html = await (await fetch("/", { cache: "no-store", headers: { accept: "text/html" } })).text();
      const published = html.match(/\/assets\/index-[\w-]+\.js/)?.[0];
      let busy = false;
      try { busy = JSON.parse(window.localStorage.getItem("img2img-active-jobs") || "[]").length > 0; } catch { /* storage blocked */ }
      if (published && !running.endsWith(published) && !busy) window.location.reload();
    } catch { /* offline or signed out: keep running */ } finally { checking = false; }
  });
}
