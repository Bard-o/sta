// Catálogo público de lugares de nacimiento (HU-01, HU-07, HU-12).
import { DEPARTAMENTOS, PAISES, municipiosDe } from "../lugares";
import { error } from "../estado";
import { http } from "../http";

export const lugaresHandlers = [
  http.get("/api/v1/lugares/paises", ({ response }) => response(200).json(PAISES)),

  http.get("/api/v1/lugares/departamentos", ({ response }) => response(200).json(DEPARTAMENTOS)),

  http.get("/api/v1/lugares/departamentos/{codigo}/municipios", ({ params, response }) => {
    if (!DEPARTAMENTOS.some((departamento) => departamento.codigo === params.codigo)) {
      return response.untyped(error(404, "no_encontrado", "El departamento no existe."));
    }
    return response(200).json(municipiosDe(params.codigo));
  }),
];
