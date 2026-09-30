import { forwardToBackend } from "@/app/lib/backendAuth";

/**
 * GET /api/backend/crypto/[...path] - Get crypto data
 * Forwarded to backend /api/crypto/:path*
 */
export async function GET(request, { params }) {
  const { path } = await params;

  // Construct the pathname from the dynamic [path] array
  const pathString = path ? path.join("/") : "";

  // Preserve query parameters from original request
  const searchParams = new URL(request.url).search;
  const backendUrl = `${process.env.NEXT_PUBLIC_API_URL}/api/crypto/${pathString}${searchParams}`;

  const response = await forwardToBackend(request, backendUrl);
  return response;
}
