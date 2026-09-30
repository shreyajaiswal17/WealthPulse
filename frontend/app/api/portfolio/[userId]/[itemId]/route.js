import { NextResponse } from "next/server";

/**
 * DEPRECATED: This route no longer uses userId in the path.
 * Backend now extracts user_id from JWT Authorization header.
 *
 * MIGRATE TO:
 * DELETE /api/backend/portfolio/[id] - Delete a holding by ID
 * The backend extracts the user_id from your Authorization token automatically.
 */

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
