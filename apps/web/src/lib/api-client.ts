export const API_URL =
  typeof window === "undefined"
    ? (process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000")
    : "/api/backend";

export async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string | { msg?: string }[];
    } | null;
    let message = `Request failed with status ${response.status}`;
    if (body?.detail) {
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        message = body.detail
          .map((item) => item?.msg)
          .filter(Boolean)
          .join("; ");
      }
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}
