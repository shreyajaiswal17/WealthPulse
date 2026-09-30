import { forwardToBackend } from "@/app/lib/backendAuth";

/**
 * DELETE /api/backend/portfolio/[id] - Delete a holding by ID (deprecated)
 * (forwarded to backend /api/portfolio/holding/:id)
 *
 * Maintained for backward compatibility. Use /api/backend/portfolio/holding/[id] for new code.
 * Backend extracts user_id from JWT Authorization header.
 */
export async function DELETE(request, { params }) {
  const { id } = await params;

  console.log(
    "[DELETE /api/backend/portfolio/:id] (deprecated, use /holding/) Holding ID:",
    id,
  );

  const backendUrl = `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/portfolio/holding/${id}`;

  return forwardToBackend(request, backendUrl, { method: "DELETE" });
}
