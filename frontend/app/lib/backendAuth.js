import { NextResponse } from "next/server";

/**
 * Extract id_token from appSession httpOnly cookie.
 * Properly handles URI-encoded cookie values and values containing "=" signs.
 * @param {Request} request - Next.js request object
 * @returns {{Authorization: string, "Content-Type": string} | null} - Headers object with Bearer token, or null if not found
 */
export function getBackendAuthHeaders(request) {
  try {
    const cookieHeader = request.headers.get("cookie") || "";

    if (!cookieHeader) {
      console.warn("[backendAuth] CRITICAL: No cookie header present at all");
      return null;
    }

    console.log(
      `[backendAuth] Cookie header found, length: ${cookieHeader.length}`,
    );

    // Split cookies properly - handles values with = signs inside
    const cookies = {};
    cookieHeader.split(";").forEach((part) => {
      const idx = part.indexOf("=");
      if (idx === -1) return;
      const key = part.slice(0, idx).trim();
      const val = part.slice(idx + 1).trim();
      cookies[key] = val;
    });

    console.log("[backendAuth] Parsed cookies, keys:", Object.keys(cookies));

    const rawSession = cookies["appSession"];
    if (!rawSession) {
      console.warn(
        "[backendAuth] CRITICAL: appSession cookie not found. Available:",
        Object.keys(cookies),
      );
      return null;
    }

    console.log(`[backendAuth] Found appSession, length: ${rawSession.length}`);

    // Decode URI encoding if present
    let sessionStr = rawSession;
    try {
      sessionStr = decodeURIComponent(rawSession);
    } catch {
      // Not URI encoded, use as-is
    }

    // Parse JSON session
    let sessionData;
    try {
      sessionData = JSON.parse(sessionStr);
    } catch (e) {
      console.warn("[backendAuth] Failed to parse appSession JSON:", e.message);
      console.warn(
        "[backendAuth] Raw session (first 100 chars):",
        sessionStr.slice(0, 100),
      );
      return null;
    }

    console.log(
      "[backendAuth] Parsed session, keys:",
      Object.keys(sessionData),
    );

    // Prefer access_token (has audience claim), fallback to id_token
    const token = sessionData.access_token || sessionData.id_token;
    if (!token) {
      console.warn(
        "[backendAuth] CRITICAL: No token found in session. Keys:",
        Object.keys(sessionData),
      );
      return null;
    }

    const tokenType = sessionData.access_token ? "access_token" : "id_token";
    console.log(
      `[backendAuth] Token extracted successfully, type: ${tokenType}, length: ${token.length}`,
    );

    const headers = {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    };

    console.log("[backendAuth] Returning auth headers with Bearer token");
    return headers;
  } catch (err) {
    console.error("[backendAuth] Unexpected error:", err.message);
    return null;
  }
}

/**
 * Forward any HTTP method (GET, POST, DELETE, PUT) to backend.
 * Auth headers are attached server-side from appSession cookie.
 * Body is only forwarded for methods that can have a body.
 */
export async function forwardToBackend(request, backendUrl, options = {}) {
  const authHeaders = await getBackendAuthHeaders(request);

  if (!authHeaders) {
    console.error(
      "[forwardToBackend] Auth extraction failed for:",
      request.method,
      backendUrl,
    );
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const method = options.method || request.method;

  // Only read body for methods that support it
  const hasBody = ["POST", "PUT", "PATCH"].includes(method.toUpperCase());

  let body = undefined;
  if (hasBody) {
    try {
      body = await request.text();
    } catch {
      body = undefined;
    }
  }

  // Merge headers: original request content-type + auth headers
  const headers = {
    "Content-Type": "application/json",
    ...authHeaders,
    ...options.headers,
  };

  try {
    const fetchOptions = {
      method,
      headers,
      ...(body !== undefined && { body }),
    };

    console.log(
      `[forwardToBackend] ${method} ${backendUrl} with Authorization: ${authHeaders.Authorization ? "Bearer token present" : "MISSING"}`,
    );

    const response = await fetch(backendUrl, fetchOptions);
    console.log(`[forwardToBackend] Response: ${response.status}`);

    // Return response as-is (pass through status + body)
    const responseBody = await response.text();
    return new NextResponse(responseBody, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("Content-Type") || "application/json",
      },
    });
  } catch (err) {
    console.error("[forwardToBackend] Fetch error:", err.message);
    return NextResponse.json(
      { error: "Backend unreachable", detail: err.message },
      { status: 502 },
    );
  }
}
