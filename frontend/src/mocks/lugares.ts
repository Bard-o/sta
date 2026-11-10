// Subconjunto del catálogo de lugares de nacimiento para la API simulada (HU-01, HU-07, HU-12).
// Los códigos y nombres son los mismos del backend; el frontend nunca los escribe a mano.
import type { Schemas } from "@/api/client";

type Lugar = Schemas["LugarNacimientoEntrada"];
type LugarSalida = Schemas["LugarNacimientoSalida"];
type Departamento = Schemas["DepartamentoSalida"];
type Municipio = Schemas["MunicipioSalida"] & { departamento: string };

export const PAISES: Schemas["PaisSalida"][] = [
  { codigo: "AR", nombre: "Argentina" },
  { codigo: "CO", nombre: "Colombia" },
  { codigo: "ES", nombre: "España" },
  { codigo: "US", nombre: "Estados Unidos" },
];

export const DEPARTAMENTOS: Departamento[] = [
  { codigo: "11", nombre: "Bogotá D. C." },
  { codigo: "17", nombre: "Caldas" },
  { codigo: "66", nombre: "Risaralda" },
  { codigo: "76", nombre: "Valle del Cauca" },
];

export const MUNICIPIOS: Municipio[] = [
  { codigo: "11001", nombre: "Bogotá D. C.", departamento: "11" },
  { codigo: "17001", nombre: "Manizales", departamento: "17" },
  { codigo: "66001", nombre: "Pereira", departamento: "66" },
  { codigo: "66682", nombre: "Santa Rosa de Cabal", departamento: "66" },
  { codigo: "76001", nombre: "Santiago de Cali", departamento: "76" },
];

export const paisDe = (codigo: string) => PAISES.find((pais) => pais.codigo === codigo);
export const departamentoDe = (codigo: string) =>
  DEPARTAMENTOS.find((departamento) => departamento.codigo === codigo);
export const municipioDe = (codigo: string) =>
  MUNICIPIOS.find((municipio) => municipio.codigo === codigo);

export const municipiosDe = (departamento: string): Schemas["MunicipioSalida"][] =>
  MUNICIPIOS.filter((municipio) => municipio.departamento === departamento).map(
    ({ codigo, nombre }) => ({ codigo, nombre }),
  );

/** El lugar de salida con nombres, como lo arma el backend. */
export function lugarSalida(lugar: Lugar): LugarSalida | null {
  const pais = paisDe(lugar.pais);
  if (!pais) return null;

  if (lugar.pais === "CO") {
    const municipio = lugar.municipio ? municipioDe(lugar.municipio) : undefined;
    const departamento = municipio ? departamentoDe(municipio.departamento) : undefined;
    if (!municipio || !departamento) return null;
    return {
      pais: pais.codigo,
      pais_nombre: pais.nombre,
      departamento: departamento.codigo,
      departamento_nombre: departamento.nombre,
      municipio: municipio.codigo,
      municipio_nombre: municipio.nombre,
      ciudad: null,
    };
  }

  return {
    pais: pais.codigo,
    pais_nombre: pais.nombre,
    departamento: null,
    departamento_nombre: null,
    municipio: null,
    municipio_nombre: null,
    ciudad: lugar.ciudad?.trim() || null,
  };
}

/** Texto para mostrar: «Santa Rosa de Cabal, Risaralda, Colombia» o «Madrid, España». */
export function textoLugar(lugar: LugarSalida): string {
  if (lugar.departamento_nombre) {
    return `${lugar.municipio_nombre}, ${lugar.departamento_nombre}, ${lugar.pais_nombre}`;
  }
  return `${lugar.ciudad}, ${lugar.pais_nombre}`;
}

/** Las mismas reglas del backend, con las claves exactas del contrato. */
export function validarLugar(lugar: Lugar | undefined): Record<string, string> {
  if (!lugar) return { "lugar_nacimiento.pais": "Elige el país de nacimiento." };
  const pais = paisDe(lugar.pais);
  if (!pais) return { "lugar_nacimiento.pais": "Elige un país de la lista." };

  const campos: Record<string, string> = {};
  if (lugar.pais === "CO") {
    if (!lugar.municipio) {
      campos["lugar_nacimiento.municipio"] = "Elige el municipio de nacimiento.";
    } else if (!municipioDe(lugar.municipio)) {
      campos["lugar_nacimiento.municipio"] = "Elige un municipio de la lista.";
    }
    if (lugar.ciudad?.trim()) {
      campos["lugar_nacimiento.ciudad"] =
        "Si naciste en Colombia, elige el municipio y deja la ciudad vacía.";
    }
    return campos;
  }

  if (lugar.municipio) {
    campos["lugar_nacimiento.municipio"] =
      "El municipio solo aplica si el país de nacimiento es Colombia.";
  }
  const ciudad = lugar.ciudad?.trim() ?? "";
  if (!ciudad) campos["lugar_nacimiento.ciudad"] = "Escribe la ciudad de nacimiento.";
  else if (ciudad.length > 120) campos["lugar_nacimiento.ciudad"] = "Es demasiado largo.";
  return campos;
}
