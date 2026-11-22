/**
 * Typed client for the clippers API.
 *
 * Types come from `schema.d.ts`, generated from the API's OpenAPI schema (`npm run gen:api`),
 * so a change to the Python models shows up here as TypeScript errors.
 *
 * The app always calls `/api/...` on its own origin. A proxy in front (Vite in development,
 * Caddy in production) forwards to the API and adds the API key, so the key never reaches
 * the browser.
 */
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export type Job = components["schemas"]["JobView"];
export type JobRequest = components["schemas"]["JobRequest"];
export type Clip = components["schemas"]["ClipView"];
export type Framing = components["schemas"]["Framing"];
export type JobState = Job["state"];

export const API_BASE = "/api";

const api = createClient<paths>({
  // Absolute (same origin): `new Request("/api/...")` needs a full URL outside browsers.
  baseUrl: `${globalThis.location?.origin ?? ""}${API_BASE}`,
  // Look `fetch` up on every call rather than once at import, so tests can replace it.
  fetch: (request) => globalThis.fetch(request),
});

/** An API failure with a human-readable message (and the form field it's about, if any). */
export class ApiError extends Error {
  readonly status: number;
  readonly field: string | undefined;

  constructor(message: string, status: number, field?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.field = field;
  }
}

type ValidationItem = { loc?: (string | number)[]; msg?: string };

/** Turn FastAPI's error bodies into one clear message. */
export function toApiError(status: number, body: unknown): ApiError {
  const detail = (body as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") {
    // e.g. "url: example.com points to a private or reserved network address"
    const match = /^(\w+): (.+)$/.exec(detail);
    return match ? new ApiError(match[2]!, status, match[1]) : new ApiError(detail, status);
  }
  if (Array.isArray(detail) && detail.length > 0) {
    // Pydantic validation errors: [{ loc: ["body", "url"], msg: "Value error, ..." }]
    const first = detail[0] as ValidationItem;
    const field = first.loc?.at(-1);
    const message = (first.msg ?? "Invalid request").replace(/^Value error, /, "");
    return new ApiError(message, status, typeof field === "string" ? field : undefined);
  }
  if (status === 401) return new ApiError("The API rejected our API key (check the proxy).", 401);
  return new ApiError(`The API answered with an error (HTTP ${status}).`, status);
}

type ApiResult<T> = { data?: T; error?: unknown; response: Response };

async function call<T>(request: () => Promise<ApiResult<T>>): Promise<T> {
  let result: ApiResult<T>;
  try {
    result = await request();
  } catch {
    throw new ApiError("Can't reach the clipper API. Is it running?", 0);
  }
  if (result.error !== undefined || result.data === undefined) {
    throw toApiError(result.response.status, result.error);
  }
  return result.data;
}

export const listJobs = (limit = 50): Promise<Job[]> =>
  call(() => api.GET("/jobs", { params: { query: { limit } } }));

export const getJob = (jobId: string): Promise<Job> =>
  call(() => api.GET("/jobs/{job_id}", { params: { path: { job_id: jobId } } }));

export const createJob = (body: JobRequest): Promise<Job> =>
  call(() => api.POST("/jobs", { body }));

/** Same-origin URL of a clip: plays in <video> and downloads through the proxy. */
export const clipUrl = (jobId: string, filename: string): string =>
  `${API_BASE}/jobs/${encodeURIComponent(jobId)}/clips/${encodeURIComponent(filename)}`;
