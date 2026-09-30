import { forwardToBackend } from "@/app/lib/backendAuth";

/**
 * GET /api/backend/ai/report - Get portfolio AI analysis report
 * Forwarded to backend /api/ai/report
 */
export async function GET(request) {
  const backendUrl = `${process.env.NEXT_PUBLIC_API_URL}/api/ai/report`;
  const response = await forwardToBackend(request, backendUrl);
  return response;
}
