/** Test helpers: render the real app at a URL, with a fake API behind `fetch`. */
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import { vi } from "vitest";
import type { Job } from "../api/client";
import { routes } from "../routes";

export function renderApp(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { router };
}

type Reply = { status?: number; body: unknown };
type Route = Reply | ((request: Request) => Reply | Promise<Reply>);

/**
 * Replace `fetch` with a fake API. Keys are "METHOD /path" (without the /api prefix).
 * Returns the mock, so tests can inspect the requests that were made.
 */
export function mockApi(routes: Record<string, Route>) {
  const fetchMock = vi.fn(async (request: Request) => {
    const path = new URL(request.url).pathname.replace(/^\/api/, "");
    const route = routes[`${request.method} ${path}`];
    if (route === undefined) {
      return Response.json({ detail: `no mock for ${request.method} ${path}` }, { status: 500 });
    }
    const reply = typeof route === "function" ? await route(request) : route;
    return Response.json(reply.body, { status: reply.status ?? 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** The JSON body of the Nth call to the fake API. */
export async function requestBody(fetchMock: ReturnType<typeof mockApi>, call: number) {
  const request = fetchMock.mock.calls[call]?.[0];
  return request ? ((await request.clone().json()) as unknown) : undefined;
}

export function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "job123",
    state: "done",
    stage: null,
    error: null,
    failed_clips: 0,
    created_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    updated_at: new Date(Date.now() - 60_000).toISOString(),
    request: {
      url: "https://cdn.example.com/streams/live-42.mp4",
      count: 5,
      duration: 30,
      framing: "blur",
      captions: true,
      language: null,
      ai: false,
    },
    clips: [],
    ...overrides,
  };
}
