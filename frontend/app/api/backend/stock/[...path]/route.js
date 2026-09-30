import { forwardToBackend } from "@/app/lib/backendAuth";

/**
 * GET /api/backend/stock/[...path] - Get stock data
 * Forwarded to backend /api/stock/:path*
 */
export async function GET(request, { params }) {
  const { path } = await params;

  // Construct the pathname from the dynamic [path] array
  const pathString = path ? path.join("/") : "";

  // Preserve query parameters from original request
  const searchParams = new URL(request.url).search;
  const backendUrl = `${process.env.NEXT_PUBLIC_API_URL}/api/stock/${pathString}${searchParams}`;

  const response = await forwardToBackend(request, backendUrl);
  return response;
}
