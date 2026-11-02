const BASE = "";

export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

function formatDetail(detail, status) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = Array.isArray(item.loc) ? item.loc.filter((p) => p !== "body").join(".") : "";
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join(" · ");
  }
  if (detail && typeof detail === "object" && detail.message) return detail.message;
  return `Request failed (${status}).`;
}

async function request(path, { method = "GET", body, signal } = {}) {
  const options = { method, headers: {}, signal };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(`${BASE}${path}`, options);
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError(
      "Cannot reach the RedditPilot server. Check that the backend is running on port 8000.",
      0
    );
  }
  if (!response.ok) {
    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    throw new ApiError(formatDetail(payload?.detail, response.status), response.status, payload);
  }
  if (response.status === 204) return null;
  const type = response.headers.get("content-type") || "";
  if (!type.includes("application/json")) return response;
  return response.json();
}

export const api = {
  get: (path, opts) => request(path, opts),
  post: (path, body = {}, opts) => request(path, { ...opts, method: "POST", body }),
  patch: (path, body = {}, opts) => request(path, { ...opts, method: "PATCH", body }),
  put: (path, body = {}, opts) => request(path, { ...opts, method: "PUT", body }),
  delete: (path, opts) => request(path, { ...opts, method: "DELETE" }),
  async download(path, fallbackName) {
    const response = await request(path);
    const blob = await response.blob();
    const disposition = response.headers.get("content-disposition") || "";
    const match = disposition.match(/filename="?([^";]+)"?/);
    const name = match ? match[1] : fallbackName;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
    return name;
  },
};

export function qs(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, value);
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}
