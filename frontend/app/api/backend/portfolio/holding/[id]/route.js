import { forwardToBackend } from "@/app/lib/backendAuth";

/**
 * DELETE /api/backend/portfolio/holding/[id] - Delete a holding by ID
 * (forwarded to backend /api/portfolio/holding/:id)
 *
 * Backend extracts user_id from JWT Authorization header.
 */
export async function DELETE(request, { params }) {
  const { id } = await params;

  console.log("[DELETE /api/backend/portfolio/holding/:id] Holding ID:", id);

  const backendUrl = `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/portfolio/holding/${id}`;

  return forwardToBackend(request, backendUrl, { method: "DELETE" });
}
