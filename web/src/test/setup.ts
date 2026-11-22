import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup(); // unmount what each test rendered
  vi.unstubAllGlobals(); // undo fetch mocks
});
