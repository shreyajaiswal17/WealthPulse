import { NextResponse } from "next/server";

/**
 * DEPRECATED: These routes no longer use userId in the path.
 * Backend now extracts user_id from JWT Authorization header.
 *
 * MIGRATE TO:
 * - GET /api/backend/portfolio - Get portfolio holdings
 * - DELETE /api/backend/portfolio/[id] - Delete a holding
 * - GET /api/backend/analytics/portfolio - Get portfolio analytics
 * - GET /api/backend/portfolio/history/[symbol] - Get buy history
 */

export async function GET(request, { params }) {
  return NextResponse.json(
    {
      detail:
        "This endpoint is deprecated. Use GET /api/backend/portfolio instead. The backend extracts the user_id from your Authorization token automatically.",
      deprecated: true,
    },
    { status: 410 },
  );
}

export async function DELETE(request, { params }) {
  return NextResponse.json(
    {
      detail:
        "This endpoint is deprecated. Use DELETE /api/backend/portfolio/[id] instead. The backend extracts the user_id from your Authorization token automatically.",
      deprecated: true,
    },
    { status: 410 },
  );
}
