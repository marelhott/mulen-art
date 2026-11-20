import { useEffect, useRef, useState } from "react";

// The input photos chosen for img2img: object URLs are released when an item goes away (or on unmount),
// and the first image's natural size drives the generation-size preview.
export function useInputImages() {
  const [inputItems, setInputItems] = useState([]);
  const [imageSize, setImageSize] = useState({ width: 1024, height: 1024 });
  const urls = useRef(new Set());
  const previewUrl = inputItems[0]?.url || "";

  useEffect(() => {
    const next = new Set(inputItems.map((item) => item.url));
    urls.current.forEach((url) => {
      if (!next.has(url)) URL.revokeObjectURL(url);
    });
    urls.current = next;
  }, [inputItems]);
  useEffect(() => () => { urls.current.forEach((url) => URL.revokeObjectURL(url)); }, []);

  useEffect(() => {
    if (!previewUrl) return undefined;
    const probe = new window.Image();
    probe.onload = () => setImageSize({ width: probe.naturalWidth, height: probe.naturalHeight });
    probe.src = previewUrl;
    return () => { probe.onload = null; };
  }, [previewUrl]);

  return { inputItems, setInputItems, imageSize };
}
