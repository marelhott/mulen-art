import { NextRequest, NextResponse } from "next/server";

// Vari spends paid API keys, so it is never public. HTTP Basic auth with the same credentials as the
// Mulen art studio (Modal secret `img2img-auth`: STUDIO_USERNAME / STUDIO_PASSWORD). It fails closed:
// without the two variables every request is refused. `next dev` (local work) skips the check.
function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export function middleware(request: NextRequest) {
  if (process.env.NODE_ENV !== "production") return NextResponse.next();
  const username = process.env.STUDIO_USERNAME;
  const password = process.env.STUDIO_PASSWORD;
  if (!username || !password) {
    return new NextResponse("Vari is not configured: STUDIO_USERNAME and STUDIO_PASSWORD are missing.", { status: 503 });
  }
  const header = request.headers.get("authorization") ?? "";
  if (header.startsWith("Basic ")) {
    try {
      const [user, ...rest] = atob(header.slice(6)).split(":");
      if (safeEqual(user, username) && safeEqual(rest.join(":"), password)) return NextResponse.next();
    } catch {
      /* malformed header: fall through to 401 */
    }
  }
  return new NextResponse("Authentication required", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Vari", charset="UTF-8"' },
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.svg|icon.svg).*)"],
};
