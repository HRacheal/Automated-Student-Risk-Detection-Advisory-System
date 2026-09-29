// Browser -> LMS backend only. The session is an HttpOnly cookie; Moodle tokens never reach this code.

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(status: number, message: string, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export const UNREACHABLE = "The LMS server is not reachable. Please try again.";

type Options = { method?: string; body?: unknown; form?: FormData; signal?: AbortSignal };

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", "X-Requested-With": "mycoach-lms" };
  let body: BodyInit | undefined;
  if (opts.form) {
    body = opts.form;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(path, { method: opts.method || (body ? "POST" : "GET"), headers, body,
                              credentials: "same-origin", signal: opts.signal });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, UNREACHABLE);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith("/api/auth/")) {
      window.dispatchEvent(new CustomEvent("lms:unauthorized"));
    }
    if (!data && res.status >= 500) throw new ApiError(res.status, UNREACHABLE);
    throw new ApiError(res.status, data?.detail || `Request failed (${res.status}).`, data?.code);
  }
  return data as T;
}
