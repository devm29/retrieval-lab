import { type NextRequest, NextResponse } from "next/server";

/**
 * The dashboard reaches the API through the /api rewrite in next.config. When the API is
 * protected with RLAB_API_TOKEN, the token is added here on the server so it never ships to
 * the browser.
 */
export function proxy(request: NextRequest) {
  const token = process.env.RLAB_API_TOKEN;
  if (!token) return NextResponse.next();
  const headers = new Headers(request.headers);
  headers.set("authorization", `Bearer ${token}`);
  return NextResponse.next({ request: { headers } });
}

export const config = {
  matcher: "/api/:path*",
};
