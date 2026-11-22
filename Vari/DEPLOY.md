# Deploy

The app is prepared for cloud storage through Cloudflare R2.

## Recommended first production setup

Use a Node-capable web host for the Next.js app and Cloudflare R2 for generated images.

Good first choices:

- Vercel or Railway for the Next.js server/API.
- Cloudflare R2 for persistent image storage shared across computers and phones.

Cloudflare-only hosting is possible later, but the app still uses `sharp` for image metadata and Comfy image normalization. That makes a standard Node runtime the safer first deployment target.

## Required environment variables

```bash
REPLICATE_API_TOKEN=
FAL_KEY=

STORAGE_DRIVER=r2
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET=variants

# Optional. If empty, images are served through /api/gallery/file?key=...
R2_PUBLIC_URL=
```

## Cloudflare R2

The bucket name expected by the app is:

```bash
variants
```

Create an R2 API token/access key with object read/write permissions for this bucket, then use those values for:

- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`

`R2_ACCOUNT_ID` is the Cloudflare account id.

## Storage behavior

In production, the app expects R2. Generated images are uploaded to R2, the gallery lists objects from R2, and delete removes the object from R2.

In local development, if `STORAGE_DRIVER` is not `r2`, the app can still fall back to `public/outputs` for quick testing.
