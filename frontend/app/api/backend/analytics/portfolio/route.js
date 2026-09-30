import { forwardToBackend } from "@/app/lib/backendAuth";

/**
 * GET /api/backend/analytics/portfolio - Get portfolio analytics with summary and holdings
 * Forwarded to backend /api/analytics/portfolio
 */
export async function GET(request) {
  const backendUrl = `${process.env.NEXT_PUBLIC_API_URL}/api/analytics/portfolio`;
  const response = await forwardToBackend(request, backendUrl);
  return response;
}
