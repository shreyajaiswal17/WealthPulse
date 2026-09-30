import { forwardToBackend } from "@/app/lib/backendAuth";

/**
 * GET /api/backend/ai/dost - Get portfolio AI Dost recommendation
 * Forwarded to backend /api/ai/dost
 */
export async function GET(request) {
  const backendUrl = `${process.env.NEXT_PUBLIC_API_URL}/api/ai/dost`;
  const response = await forwardToBackend(request, backendUrl);
  return response;
}
