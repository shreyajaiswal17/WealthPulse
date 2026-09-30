import { forwardToBackend } from "@/app/lib/backendAuth";

/**
 * GET /api/backend/portfolio - Get portfolio holdings for current user (forwarded to backend /api/portfolio)
 * POST /api/backend/portfolio - Add a new holding (forwarded to backend /api/portfolio)
 *
 * Backend now extracts user_id from JWT, so no need for path parameters
 */
export async function GET(request) {
  const backendUrl = `${process.env.NEXT_PUBLIC_API_URL}/api/portfolio`;
  console.log("GET portfolio from backend:", backendUrl);
  const response = await forwardToBackend(request, backendUrl);
  return response;
}

export async function POST(request) {
  const backendUrl = `${process.env.NEXT_PUBLIC_API_URL}/api/portfolio`;
  console.log("POST holding to backend:", backendUrl);
  const response = await forwardToBackend(request, backendUrl);
  return response;
}
