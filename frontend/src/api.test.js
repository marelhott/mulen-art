// Run: node --test frontend/src/api.test.js
import { test } from "node:test";
import assert from "node:assert/strict";
import { buildImageUrl, formatDuration, imageUrl, sourceUrl, thumbUrl } from "./api.js";

test("buildImageUrl keeps absolute URLs and prefixes relative paths", () => {
  assert.equal(buildImageUrl("/library/a.png"), "/library/a.png");
  assert.equal(buildImageUrl("https://example.test/a.png"), "https://example.test/a.png");
  assert.equal(buildImageUrl("data:image/png;base64,AAA"), "data:image/png;base64,AAA");
  assert.equal(buildImageUrl(""), "");
});

test("grids use the thumbnail while the viewer uses the full image", () => {
  const saved = { url: "/library/full.png", thumb_url: "/thumb/full.webp" };
  assert.equal(thumbUrl(saved), "/thumb/full.webp");
  assert.equal(imageUrl(saved), "/library/full.png");
  // Records written before thumbnails existed still render.
  const legacy = { url: "/library/old.png" };
  // A stored file without thumb_url still gets a derived preview path.
  assert.equal(thumbUrl(legacy), "/thumb/old.webp");
  assert.equal(imageUrl(legacy), "/library/old.png");
});

test("local uploads never receive a server thumbnail path", () => {
  const upload = { id: "x", src: "blob:http://localhost/abc", filename: "photo.png" };
  assert.equal(thumbUrl(upload), "blob:http://localhost/abc");
});

test("in-memory results without a URL fall back to embedded base64", () => {
  const inline = { image_base64: "AAA", format: "webp" };
  assert.equal(imageUrl(inline), "data:image/webp;base64,AAA");
  assert.equal(thumbUrl(inline), "data:image/webp;base64,AAA");
});

test("sourceUrl resolves retained inputs and returns empty otherwise", () => {
  assert.equal(sourceUrl({ source_url: "/library/src.png" }), "/library/src.png");
  assert.equal(sourceUrl({ settings: { source_url: "/library/nested.png" } }), "/library/nested.png");
  assert.equal(sourceUrl({}), "");
  assert.equal(sourceUrl(null), "");
});

test("imageUrl prefers an already resolved src", () => {
  assert.equal(imageUrl({ src: "blob:xyz", url: "/library/a.png" }), "blob:xyz");
});

test("formatDuration switches to minutes past sixty seconds", () => {
  assert.equal(formatDuration(9.7), "9 s");
  assert.equal(formatDuration(125), "2 min 5 s");
  assert.equal(formatDuration(undefined), "0 s");
});
