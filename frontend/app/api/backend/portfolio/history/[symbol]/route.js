import { forwardToBackend } from "@/app/lib/backendAuth";
import { NextResponse } from "next/server";

/**
 * GET /api/backend/portfolio/history/[symbol] - Get buy history for a specific symbol
 * Forwards to backend: GET /api/portfolio/history/{symbol}
 */
export async function GET(request, { params }) {
  try {
    const { symbol } = await params;
    console.log("[history] Symbol param:", symbol);

    const backendUrl = `${process.env.NEXT_PUBLIC_API_URL}/api/portfolio/history/${encodeURIComponent(symbol)}`;
    console.log("[history] Backend URL:", backendUrl);

    const response = await forwardToBackend(request, backendUrl);
    console.log("[history] Response status:", response.status);
    return response;
  } catch (error) {
    console.error("[history] Error:", error.message);
    return NextResponse.json(
      { error: "Failed to fetch history", detail: error.message },
      { status: 500 },
    );
  }
}
