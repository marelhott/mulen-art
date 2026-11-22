import {
  DeleteObjectCommand,
  GetObjectCommand,
  ListObjectsV2Command,
  PutObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { mkdir, readdir, rm, stat, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { Readable } from "node:stream";

const OUTPUT_DIR = path.join(process.cwd(), "public", "outputs");
const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".webp"]);

export type GalleryImage = {
  id: string;
  url: string;
  jobId: string;
  name: string;
  createdAt: string;
  size: number;
};

function isR2Enabled() {
  return process.env.STORAGE_DRIVER === "r2" || process.env.NODE_ENV === "production";
}

function getR2Config() {
  const accountId = process.env.R2_ACCOUNT_ID;
  const accessKeyId = process.env.R2_ACCESS_KEY_ID;
  const secretAccessKey = process.env.R2_SECRET_ACCESS_KEY;
  const bucket = process.env.R2_BUCKET;

  if (!accountId || !accessKeyId || !secretAccessKey || !bucket) {
    throw new Error("R2 storage není kompletně nastavený.");
  }

  return {
    bucket,
    publicUrl: process.env.R2_PUBLIC_URL?.replace(/\/$/, ""),
    client: new S3Client({
      region: "auto",
      endpoint: `https://${accountId}.r2.cloudflarestorage.com`,
      credentials: {
        accessKeyId,
        secretAccessKey,
      },
    }),
  };
}

function extensionFromContentType(contentType: string) {
  if (contentType.includes("jpeg") || contentType.includes("jpg")) return "jpg";
  if (contentType.includes("webp")) return "webp";
  return "png";
}

function keyToUrl(key: string) {
  const publicUrl = process.env.R2_PUBLIC_URL?.replace(/\/$/, "");

  if (isR2Enabled() && publicUrl) {
    return `${publicUrl}/${key.split("/").map(encodeURIComponent).join("/")}`;
  }

  if (isR2Enabled()) {
    return `/api/gallery/file?key=${encodeURIComponent(key)}`;
  }

  return `/outputs/${key.split("/").map(encodeURIComponent).join("/")}`;
}

function getLocalPathFromUrl(url: string) {
  const normalized = decodeURIComponent(url).replaceAll("\\", "/");

  if (!normalized.startsWith("/outputs/")) {
    throw new Error("Neplatná cesta k obrázku.");
  }

  const relative = normalized.replace(/^\/outputs\//, "");
  const filePath = path.join(OUTPUT_DIR, relative);
  const resolved = path.resolve(filePath);
  const outputRoot = path.resolve(OUTPUT_DIR);

  if (!resolved.startsWith(outputRoot)) {
    throw new Error("Neplatná cesta k obrázku.");
  }

  return resolved;
}

function keyFromUrl(url: string) {
  if (url.startsWith("/api/gallery/file?")) {
    const parsed = new URL(url, "http://local");
    const key = parsed.searchParams.get("key");

    if (!key) {
      throw new Error("Chybí key obrázku.");
    }

    return key;
  }

  const publicUrl = process.env.R2_PUBLIC_URL?.replace(/\/$/, "");

  if (publicUrl && url.startsWith(`${publicUrl}/`)) {
    return decodeURIComponent(url.slice(publicUrl.length + 1));
  }

  if (url.startsWith("/outputs/")) {
    return decodeURIComponent(url.replace(/^\/outputs\//, ""));
  }

  throw new Error("Neplatná cesta k obrázku.");
}

async function streamToBuffer(stream: ReadableStream | Readable) {
  const chunks: Buffer[] = [];

  for await (const chunk of stream as AsyncIterable<Uint8Array>) {
    chunks.push(Buffer.from(chunk));
  }

  return Buffer.concat(chunks);
}

export async function saveRemoteImage(url: string, jobId: string, index: number) {
  let response: Response | null = null;
  let lastError: unknown;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      response = await fetch(url);
      if (response.ok) break;
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 800 * (attempt + 1)));
  }

  if (!response) {
    throw lastError instanceof Error ? lastError : new Error("Stažení obrázku selhalo.");
  }

  if (!response.ok) {
    return url;
  }

  const contentType = response.headers.get("content-type") || "image/png";
  const buffer = Buffer.from(await response.arrayBuffer());
  const extension = extensionFromContentType(contentType);
  const fileName = `variant-${String(index + 1).padStart(2, "0")}.${extension}`;
  const key = `${jobId}/${fileName}`;

  if (isR2Enabled()) {
    const { bucket, client } = getR2Config();

    await client.send(
      new PutObjectCommand({
        Bucket: bucket,
        Key: key,
        Body: buffer,
        ContentType: contentType,
      }),
    );

    return keyToUrl(key);
  }

  const jobDir = path.join(OUTPUT_DIR, jobId);

  await mkdir(jobDir, { recursive: true });
  await writeFile(path.join(jobDir, fileName), buffer);

  return keyToUrl(key);
}

export async function saveBufferImage(
  buffer: Buffer,
  jobId: string,
  index: number,
  contentType = "image/png",
) {
  const extension = extensionFromContentType(contentType);
  const fileName = `variant-${String(index + 1).padStart(2, "0")}.${extension}`;
  const key = `${jobId}/${fileName}`;

  if (isR2Enabled()) {
    const { bucket, client } = getR2Config();

    await client.send(
      new PutObjectCommand({
        Bucket: bucket,
        Key: key,
        Body: buffer,
        ContentType: contentType,
      }),
    );

    return keyToUrl(key);
  }

  const jobDir = path.join(OUTPUT_DIR, jobId);
  await mkdir(jobDir, { recursive: true });
  await writeFile(path.join(jobDir, fileName), buffer);
  return keyToUrl(key);
}

export async function listGalleryImages() {
  if (isR2Enabled()) {
    const { bucket, client } = getR2Config();
    const response = await client.send(new ListObjectsV2Command({ Bucket: bucket }));

    return (response.Contents || [])
      .filter((item) => item.Key && IMAGE_EXTENSIONS.has(path.extname(item.Key).toLowerCase()))
      .map((item) => {
        const key = item.Key || "";
        const [jobId, name] = key.split("/");

        return {
          id: key,
          url: keyToUrl(key),
          jobId: jobId || "outputs",
          name: name || key,
          createdAt: (item.LastModified || new Date()).toISOString(),
          size: item.Size || 0,
        };
      })
      .sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt));
  }

  const images: GalleryImage[] = [];
  let jobDirs: string[] = [];

  try {
    jobDirs = await readdir(OUTPUT_DIR);
  } catch {
    return images;
  }

  for (const jobId of jobDirs) {
    const jobDir = path.join(OUTPUT_DIR, jobId);
    const jobStat = await stat(jobDir).catch(() => null);

    if (!jobStat?.isDirectory()) {
      continue;
    }

    const files = await readdir(jobDir).catch(() => []);

    for (const file of files) {
      const extension = path.extname(file).toLowerCase();

      if (!IMAGE_EXTENSIONS.has(extension)) {
        continue;
      }

      const filePath = path.join(jobDir, file);
      const fileStat = await stat(filePath).catch(() => null);

      if (!fileStat?.isFile()) {
        continue;
      }

      const key = `${jobId}/${file}`;

      images.push({
        id: key,
        url: keyToUrl(key),
        jobId,
        name: file,
        createdAt: fileStat.mtime.toISOString(),
        size: fileStat.size,
      });
    }
  }

  return images.sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt));
}

export async function deleteGalleryImage(url: string) {
  if (isR2Enabled()) {
    const key = keyFromUrl(url);
    const { bucket, client } = getR2Config();

    await client.send(new DeleteObjectCommand({ Bucket: bucket, Key: key }));
    return;
  }

  const filePath = getLocalPathFromUrl(url);
  const jobDir = path.dirname(filePath);

  await unlink(filePath);

  const remaining = await readdir(jobDir).catch(() => []);
  if (!remaining.length) {
    await rm(jobDir, { recursive: true, force: true });
  }
}

export async function readGalleryImage(key: string) {
  if (!isR2Enabled()) {
    throw new Error("Proxy obrázků je dostupný jen pro R2 storage.");
  }

  const { bucket, client } = getR2Config();
  const response = await client.send(new GetObjectCommand({ Bucket: bucket, Key: key }));

  if (!response.Body) {
    throw new Error("Obrázek nebyl nalezen.");
  }

  const body = await streamToBuffer(response.Body as Readable);

  return {
    body,
    contentType: response.ContentType || "image/png",
  };
}
