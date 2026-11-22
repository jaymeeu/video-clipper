import { describe, expect, it } from "vitest";
import { toApiError } from "../api/client";
import { clock, isWebUrl, length, reasonParts, shortUrl, timeAgo } from "./format";

describe("format helpers", () => {
  const now = Date.parse("2026-11-22T12:00:00Z");

  it.each([
    ["2026-11-22T11:59:40Z", "just now"],
    ["2026-11-22T11:55:00Z", "5 minutes ago"],
    ["2026-11-22T09:00:00Z", "3 hours ago"],
    ["2026-11-21T12:00:00Z", "yesterday"],
  ])("timeAgo(%s) = %s", (iso, expected) => {
    expect(timeAgo(iso, now)).toBe(expected);
  });

  it.each([
    [0, "0:00"],
    [83, "1:23"],
    [378.84, "6:18"],
    [3725, "1:02:05"],
  ])("clock(%d) = %s", (seconds, expected) => {
    expect(clock(seconds)).toBe(expected);
  });

  it.each([
    [43.46, "43s"],
    [75, "1m 15s"],
  ])("length(%d) = %s", (seconds, expected) => {
    expect(length(seconds)).toBe(expected);
  });

  it("shortUrl drops www and the scheme, and truncates", () => {
    expect(shortUrl("https://www.youtube.com/watch?v=R6MlUcmOul8")).toBe(
      "youtube.com/watch?v=R6MlUcmOul8",
    );
    expect(shortUrl("https://cdn.example.com/a/very/long/path/to/the/recording.mp4", 20)).toBe(
      "cdn.example.com/a/v…",
    );
  });

  it.each([
    ["https://example.com/v.mp4", true],
    ["http://example.com", true],
    ["  https://example.com/x  ", true],
    ["example.com/v.mp4", false],
    ["ftp://example.com/v.mp4", false],
    ["file:///etc/passwd", false],
    ["", false],
  ])("isWebUrl(%j) = %s", (value, expected) => {
    expect(isWebUrl(value)).toBe(expected);
  });

  it("reasonParts splits the API's reason string", () => {
    expect(reasonParts("AI 8/10 \"Big win\": funny; 5 reactions ('omo'); 3.2 dB louder")).toEqual([
      'AI 8/10 "Big win": funny',
      "5 reactions ('omo')",
      "3.2 dB louder",
    ]);
    expect(reasonParts(null)).toEqual([]);
  });
});

describe("toApiError", () => {
  it("reads FastAPI's field-prefixed message", () => {
    const error = toApiError(422, {
      detail: "url: x.com points to a private or reserved network address",
    });
    expect(error.field).toBe("url");
    expect(error.message).toBe("x.com points to a private or reserved network address");
  });

  it("reads pydantic validation errors", () => {
    const error = toApiError(422, {
      detail: [
        { loc: ["body", "url"], msg: "Value error, must be an http(s) URL", type: "value_error" },
      ],
    });
    expect(error.field).toBe("url");
    expect(error.message).toBe("must be an http(s) URL");
  });

  it("explains a rejected API key", () => {
    expect(toApiError(401, {}).message).toMatch(/API key/);
  });
});
