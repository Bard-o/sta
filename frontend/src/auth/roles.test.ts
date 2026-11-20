import { esRutaInterna } from "@/auth/roles";

describe("esRutaInterna (HU-02, contrato de la iteración 2)", () => {
  // HU-02: son las rutas a las que la aplicación vuelve tras verificar el correo o iniciar sesión.
  it.each([
    "/",
    "/cliente",
    "/compra/viajeros?seleccion=71",
    "/mis-viajes?tipo=reserva&pagar=41",
    "/verificar-correo?volver=%2Fcompra%2Fviajeros%3Fseleccion%3D71",
  ])("HU-02: acepta la ruta interna %j", (ruta) => {
    expect(esRutaInterna(ruta)).toBe(true);
  });

  // HU-02: el navegador quita `\t`, `\n` y `\r` al resolver una URL y lee `\` como `/`, así que
  // estas rutas terminarían en otro sitio al abrirlas con Ctrl+clic o clic medio en un enlace.
  it.each([
    "https://malicioso.example",
    "//malicioso.example",
    "/\\malicioso.example",
    "/a\\b",
    "/\t/malicioso.example",
    "/\n/malicioso.example",
    "/\r/malicioso.example",
    "/cliente\t",
    "/\r\n/malicioso.example",
  ])("HU-02: rechaza %j", (ruta) => {
    expect(esRutaInterna(ruta)).toBe(false);
  });

  it("HU-02: rechaza lo que no es texto o está vacío", () => {
    // HU-02: sin `volver` ni `next` la pantalla se comporta como siempre.
    expect(esRutaInterna(null)).toBe(false);
    expect(esRutaInterna(undefined)).toBe(false);
    expect(esRutaInterna("")).toBe(false);
    expect(esRutaInterna("cliente")).toBe(false);
  });
});
