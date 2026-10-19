import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";

// openapi-fetch toma `fetch` al crear el cliente: se reemplaza antes de importar la app y cada
// test define sus respuestas con `responderApi` (src/test/api.ts).
vi.stubGlobal("fetch", vi.fn());

afterEach(() => {
  cleanup();
  vi.mocked(fetch).mockReset();
});
