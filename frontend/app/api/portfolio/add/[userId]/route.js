import { NextResponse } from "next/server";

/**
 * DEPRECATED: This route no longer uses userId in the path.
 * Backend now extracts user_id from JWT Authorization header.
 *
 * MIGRATE TO:
 * POST /api/backend/portfolio - Add a new holding
 * The backend extracts the user_id from your Authorization token automatically.
 */

export async function POST(request, { params }) {
  return NextResponse.json(
    {
      detail:
        "This endpoint is deprecated. Use POST /api/backend/portfolio instead. The backend extracts the user_id from your Authorization token automatically.",
      deprecated: true,
    },
    { status: 410 },
  );
}
