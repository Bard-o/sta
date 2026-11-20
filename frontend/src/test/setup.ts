import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";

// jsdom no implementa estas APIs, que cmdk usa para medir y desplazar la lista del Combobox.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    constructor(callback: ResizeObserverCallback) {
      void callback;
    }
    observe(target: Element, options?: ResizeObserverOptions) {
      void target;
      void options;
    }
    unobserve(target: Element) {
      void target;
    }
    disconnect() {}
  };
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// openapi-fetch toma `fetch` al crear el cliente: se reemplaza antes de importar la app y cada
// test define sus respuestas con `responderApi` (src/test/api.ts).
vi.stubGlobal("fetch", vi.fn());

afterEach(() => {
  cleanup();
  vi.mocked(fetch).mockReset();
  // HU-02: la copia del destino de la verificación (`sta-regreso-verificacion`) y el resto de
  // lo que una pantalla guarde en el navegador no pasan de un test al siguiente.
  localStorage.clear();
});
