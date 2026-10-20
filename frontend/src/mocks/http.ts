// `http` de MSW tipado con el contrato: solo acepta rutas de schema.d.ts y obliga a que cada
// respuesta tenga el cuerpo del status declarado. Los errores van con `response.untyped(...)`.
import { createOpenApiHttp } from "openapi-msw";
import type { paths } from "@/api/schema";

export const http = createOpenApiHttp<paths>();
