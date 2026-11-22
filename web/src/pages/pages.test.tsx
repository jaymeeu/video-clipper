import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { makeJob, mockApi, renderApp, requestBody } from "../test/helpers";

const clip = (n: number, title: string | null) => ({
  filename: `0${n}-clip.mp4`,
  start: 60 * n,
  duration: 31.5,
  title,
  reason: n === 1 ? "AI 8/10 \"Big win\": the payoff; 5 reactions ('omo', 'chai')" : null,
  score: 3 - n,
  url: `http://api.internal/jobs/job123/clips/0${n}-clip.mp4`,
});

describe("Jobs page", () => {
  it("lists jobs newest first with a summary of each", async () => {
    mockApi({
      "GET /jobs": {
        body: [
          makeJob({ id: "a", state: "running", stage: "transcribing" }),
          makeJob({ id: "b", state: "done", clips: [clip(1, "x"), clip(2, "y")] }),
          makeJob({ id: "c", state: "failed", error: "could not download: HTTP 404" }),
        ],
      },
    });

    renderApp("/");

    const rows = await screen.findAllByRole("link", { name: /cdn\.example\.com/ });
    expect(rows).toHaveLength(3);
    expect(within(rows[0]!).getByText("Transcribe…")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("2 clips ready")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("could not download: HTTP 404")).toBeInTheDocument();
    expect(rows[0]).toHaveAttribute("href", "/jobs/a");
    expect(screen.getByText("Updating live")).toBeInTheDocument(); // a job is running
  });

  it("invites you to make clips when there are no jobs", async () => {
    mockApi({ "GET /jobs": { body: [] } });

    renderApp("/");

    expect(await screen.findByText("No clips yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /make your first clips/i })).toHaveAttribute(
      "href",
      "/new",
    );
  });

  it("shows a retryable error when the API is down", async () => {
    mockApi({ "GET /jobs": { status: 503, body: {} } });

    renderApp("/");

    expect(await screen.findByText("Couldn't load jobs")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});

describe("New clips page", () => {
  it("checks the link before sending anything", async () => {
    const api = mockApi({});
    renderApp("/new");

    await userEvent.type(screen.getByLabelText("Video link"), "not a link");
    await userEvent.click(screen.getByRole("button", { name: /make clips/i }));

    expect(screen.getByRole("alert")).toHaveTextContent(/doesn't look like a web link/);
    expect(api).not.toHaveBeenCalled();
  });

  it("sends the chosen options and opens the new job", async () => {
    const created = makeJob({ id: "new1", state: "queued", clips: [] });
    const api = mockApi({
      "POST /jobs": { status: 202, body: created },
      "GET /jobs/new1": { body: created },
    });
    const { router } = renderApp("/new");

    await userEvent.type(screen.getByLabelText("Video link"), "https://cdn.example.com/rec.mp4");
    await userEvent.click(screen.getByRole("radio", { name: "8" }));
    await userEvent.click(screen.getByRole("radio", { name: "45s" }));
    await userEvent.click(screen.getByRole("radio", { name: /fill the screen/i }));
    await userEvent.click(screen.getByRole("switch", { name: /ai picks/i }));
    await userEvent.click(screen.getByRole("button", { name: /make clips/i }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/jobs/new1"));
    expect(await requestBody(api, 0)).toEqual({
      url: "https://cdn.example.com/rec.mp4",
      count: 8,
      duration: 45,
      framing: "crop",
      captions: true,
      ai: true,
      language: null,
    });
    expect(await screen.findByText("Queued")).toBeInTheDocument();
  });

  it("shows the API's reason under the link field", async () => {
    mockApi({
      "POST /jobs": {
        status: 422,
        body: { detail: "url: intranet.local points to a private or reserved network address" },
      },
    });
    renderApp("/new");

    await userEvent.type(screen.getByLabelText("Video link"), "https://intranet.local/v.mp4");
    await userEvent.click(screen.getByRole("button", { name: /make clips/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "intranet.local points to a private or reserved network address",
    );
    expect(screen.getByLabelText("Video link")).toHaveAttribute("aria-invalid", "true");
  });
});

describe("Job page", () => {
  it("shows progress while the worker runs", async () => {
    mockApi({ "GET /jobs/job123": { body: makeJob({ state: "running", stage: "transcribing" }) } });

    renderApp("/jobs/job123");

    const current = await screen.findByText("Transcribe");
    expect(current.closest("[aria-current]")).toHaveAttribute("aria-current", "step");
    expect(screen.getByText(/You can leave this page/)).toBeInTheDocument();
  });

  it("lists clips you can watch and download, with why they were picked", async () => {
    mockApi({
      "GET /jobs/job123": {
        body: makeJob({ clips: [clip(1, "Big win"), clip(2, null)], failed_clips: 1 }),
      },
    });

    renderApp("/jobs/job123");

    expect(await screen.findByRole("heading", { name: "2 clips" })).toBeInTheDocument();
    const player = screen.getByLabelText("Clip 1: Big win");
    expect(player.tagName).toBe("VIDEO");
    // Same-origin URL through the proxy, not the API's own (internal) address:
    expect(player).toHaveAttribute("src", "/api/jobs/job123/clips/01-clip.mp4#t=0.1");
    const downloads = screen.getAllByRole("link", { name: /download/i });
    expect(downloads[0]).toHaveAttribute("href", "/api/jobs/job123/clips/01-clip.mp4");
    expect(downloads[0]).toHaveAttribute("download", "01-clip.mp4");
    expect(screen.getByText("Moment at 2:00")).toBeInTheDocument(); // untitled clip
    expect(screen.getByText(/1 more couldn't be rendered/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /why this clip/i }));
    expect(screen.getByText("5 reactions ('omo', 'chai')")).toBeInTheDocument();
  });

  it("explains a failure and can run the same request again", async () => {
    const failed = makeJob({ state: "failed", error: "could not download: HTTP 404" });
    const again = makeJob({ id: "job456", state: "queued" });
    const api = mockApi({
      "GET /jobs/job123": { body: failed },
      "POST /jobs": { status: 202, body: again },
      "GET /jobs/job456": { body: again },
    });
    const { router } = renderApp("/jobs/job123");

    expect(await screen.findByText("could not download: HTTP 404")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /run it again/i }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/jobs/job456"));
    const post = api.mock.calls.findIndex(([request]) => request.method === "POST");
    expect(await requestBody(api, post)).toEqual(failed.request);
  });

  it("says when a job no longer exists", async () => {
    mockApi({ "GET /jobs/gone": { status: 404, body: { detail: "no such job" } } });

    renderApp("/jobs/gone");

    expect(await screen.findByText("Job not found")).toBeInTheDocument();
    expect(screen.getByText(/deleted after 7 days/)).toBeInTheDocument();
  });
});
