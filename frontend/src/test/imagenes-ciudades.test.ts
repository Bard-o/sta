/// <reference types="node" />
// HU-13 · HU-19 · RF-22 · SUP-30: banco de imágenes por ciudad destino.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { CIUDADES } from "@/mocks/datos";

// Código → ciudad del catálogo (RF-12). Fuente: `_CIUDADES` en la migración
// backend/alembic/versions/2026_10_22_1940-8769cb0e0baf_vuelos_crea_ciudades_y_vuelos.py.
// El contenedor del frontend no monta backend/, por eso se copia aquí.
const CATALOGO: Record<string, string> = {
  LET: "Leticia",
  MDE: "Medellín",
  AUC: "Arauca",
  BAQ: "Barranquilla",
  CTG: "Cartagena",
  GUS: "Tunja",
  MZL: "Manizales",
  FLA: "Florencia",
  EYP: "Yopal",
  PPN: "Popayán",
  VUP: "Valledupar",
  MTR: "Montería",
  BOG: "Bogotá",
  UIB: "Quibdó",
  RCH: "Riohacha",
  NVA: "Neiva",
  SMR: "Santa Marta",
  VVC: "Villavicencio",
  PSO: "Pasto",
  CUC: "Cúcuta",
  VGZ: "Mocoa",
  AXM: "Armenia",
  PEI: "Pereira",
  ADZ: "San Andrés",
  BGA: "Bucaramanga",
  CZU: "Sincelejo",
  IBE: "Ibagué",
  CLO: "Cali",
  MVP: "Mitú",
  PCR: "Puerto Carreño",
  PDA: "Inírida",
  SJE: "San José del Guaviare",
  MAD: "Madrid",
  LHR: "Londres",
  JFK: "Nueva York",
  EZE: "Buenos Aires",
  MIA: "Miami",
};

const CARPETA = import.meta.dirname
  ? path.resolve(import.meta.dirname, "../../public/imagenes/ciudades")
  : path.resolve(process.cwd(), "public/imagenes/ciudades");
const LIMITE_BYTES = 300_000;
const LICENCIA_PERMITIDA =
  /^(CC0( 1\.0)?|Dominio público|CC BY(-SA)? (1\.0|2\.0|2\.5|3\.0|4\.0)( [a-z]{2,3})?)$/;

type Fila = {
  codigo: string;
  ciudad: string;
  fuente: string;
  autor: string;
  licencia: string;
};

// Filas de la tabla de LICENCIAS.md: `| Código | Ciudad | Fuente | Autor | Licencia |`.
function filasLicencias(): Fila[] {
  const texto = readFileSync(path.join(CARPETA, "LICENCIAS.md"), "utf8");
  return texto.split("\n").flatMap((linea) => {
    const celdas = linea
      .trim()
      .replace(/^\||\|$/g, "")
      .split(/(?<!\\)\|/)
      .map((c) => c.trim());
    if (celdas.length !== 5 || !/^[A-Z]{3}$/.test(celdas[0])) return [];
    const [codigo, ciudad, fuente, autor, licencia] = celdas;
    return [{ codigo, ciudad, fuente, autor, licencia }];
  });
}

describe("banco de imágenes por ciudad (SUP-30)", () => {
  const codigos = Object.keys(CATALOGO);

  it("el catálogo de referencia tiene las 37 ciudades", () => {
    expect(codigos).toHaveLength(37);
  });

  it.each(codigos)("%s tiene un JPG de menos de 300 KB", (codigo) => {
    const archivo = path.join(CARPETA, `${codigo}.jpg`);
    expect(existsSync(archivo), `falta ${codigo}.jpg`).toBe(true);
    expect(statSync(archivo).size).toBeLessThan(LIMITE_BYTES);
    const firma = readFileSync(archivo).subarray(0, 3);
    expect([...firma]).toEqual([0xff, 0xd8, 0xff]);
  });

  it("no hay JPG de ciudades que no estén en el catálogo", () => {
    const jpgs = readdirSync(CARPETA)
      .filter((nombre) => nombre.endsWith(".jpg"))
      .map((nombre) => nombre.replace(/\.jpg$/, ""))
      .sort();
    expect(jpgs).toEqual([...codigos].sort());
  });

  describe("LICENCIAS.md", () => {
    const filas = filasLicencias();

    it.each(codigos)("%s registra fuente, autor y licencia libre", (codigo) => {
      const fila = filas.find((f) => f.codigo === codigo);
      expect(fila, `falta la fila de ${codigo} en LICENCIAS.md`).toBeDefined();
      expect(fila?.ciudad).toBe(CATALOGO[codigo]);
      expect(fila?.fuente).toMatch(/\]\(https:\/\/commons\.wikimedia\.org\/wiki\/File:/);
      expect(fila?.autor).not.toBe("");
      const licencia = /^\[([^\]]+)\]\(https:\/\/[^)\s]+\)$/.exec(fila?.licencia ?? "");
      expect(licencia, `licencia sin formato [nombre](url): ${fila?.licencia}`).not.toBeNull();
      expect(licencia?.[1]).toMatch(LICENCIA_PERMITIDA);
    });

    it("no repite códigos", () => {
      expect(filas).toHaveLength(codigos.length);
    });
  });

  it("las ciudades de la API simulada apuntan a una imagen que existe", () => {
    for (const ciudad of CIUDADES) {
      expect(ciudad.imagen_url).toBe(`/imagenes/ciudades/${ciudad.codigo}.jpg`);
      expect(existsSync(path.join(CARPETA, `${ciudad.codigo}.jpg`))).toBe(true);
    }
  });
});
