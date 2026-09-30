import { forwardToBackend } from "@/app/lib/backendAuth";

/**
 * GET /api/backend/market/[...path] - Get market data for mutual funds, stocks, crypto, prices
 * Forwarded to backend /api/market/:path*
 */
export async function GET(request, { params }) {
  const { path } = await params;

  // Construct the pathname from the dynamic [path] array
  const pathString = path ? path.join("/") : "";

  // Preserve query parameters from original request
  const searchParams = new URL(request.url).search;
  const backendUrl = `${process.env.NEXT_PUBLIC_API_URL}/api/market/${pathString}${searchParams}`;

  const response = await forwardToBackend(request, backendUrl);
  return response;
}
