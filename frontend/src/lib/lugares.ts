import { useQuery } from "@tanstack/react-query";
import { api, unwrap, type Schemas } from "@/api/client";

export type Pais = Schemas["PaisSalida"];
export type Departamento = Schemas["DepartamentoSalida"];
export type Municipio = Schemas["MunicipioSalida"];

/** Lo que guarda el formulario: el mismo objeto de `LugarNacimientoEntrada`. */
export type LugarFormulario = {
  pais: string;
  municipio: string | null;
  ciudad: string | null;
};

export const LUGAR_VACIO: LugarFormulario = { pais: "", municipio: null, ciudad: null };

// El catálogo solo cambia con un despliegue y el backend lo cachea un día. En memoria dura lo
// mismo: no se vuelve a pedir al abrir otro formulario.
const CACHE_CATALOGO = 24 * 60 * 60 * 1000;

export const LUGARES_KEY = ["lugares"] as const;

/** Países ISO 3166-1 con nombres en español (HU-01, HU-07, HU-12). */
export function usePaises() {
  return useQuery({
    queryKey: [...LUGARES_KEY, "paises"],
    queryFn: () => unwrap(api.GET("/api/v1/lugares/paises")),
    staleTime: CACHE_CATALOGO,
    gcTime: CACHE_CATALOGO,
  });
}

/** Departamentos de la DIVIPOLA, incluida Bogotá D. C. */
export function useDepartamentos() {
  return useQuery({
    queryKey: [...LUGARES_KEY, "departamentos"],
    queryFn: () => unwrap(api.GET("/api/v1/lugares/departamentos")),
    staleTime: CACHE_CATALOGO,
    gcTime: CACHE_CATALOGO,
  });
}

/** Municipios de un departamento. Sin departamento no se pide nada. */
export function useMunicipios(departamento: string) {
  return useQuery({
    queryKey: [...LUGARES_KEY, "municipios", departamento],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/lugares/departamentos/{codigo}/municipios", {
          params: { path: { codigo: departamento } },
        }),
      ),
    enabled: departamento !== "",
    staleTime: CACHE_CATALOGO,
    gcTime: CACHE_CATALOGO,
  });
}

/** Departamento al que pertenece un municipio: los dos primeros dígitos del código. */
export const departamentoDeMunicipio = (municipio: string) => municipio.slice(0, 2);

/** Opciones para el Combobox; el nombre es lo que se busca y el código lo que se guarda. */
export const opcionesDe = (items: { codigo: string; nombre: string }[] | undefined) =>
  (items ?? []).map((item) => ({ value: item.codigo, label: item.nombre }));
