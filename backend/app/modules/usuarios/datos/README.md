# Catálogo de lugares de nacimiento

Datos estáticos que usa el módulo `usuarios` para el campo `lugar_nacimiento` (HU-01, HU-07 y
HU-12). Se cargan una sola vez al importar el módulo (`catalogos.py`) y no cambian en ejecución.

## `paises.json`

- **Fuente:** lista ISO 3166-1 alpha-2 con nombres en español del repositorio
  [`umpirsky/country-list`](https://github.com/umpirsky/country-list), archivo
  `data/es/country.json`.
- **Descarga:** 2026-11-09.
- **Contenido:** 249 países, ordenados por nombre. Cada uno tiene `codigo` (ISO alpha-2 en
  mayúsculas) y `nombre` en español.

## `divipola.json`

- **Fuente:** DIVIPOLA del DANE, dataset
  [`gdxc-w37w` «DIVIPOLA - Códigos Municipios»](https://www.datos.gov.co/Estad-sticas-Nacionales/DIVIPOLA-C-digos-Municipios/gdxc-w37w)
  de datos.gov.co (datos abiertos).
- **Descarga:** 2026-11-09.
- **Contenido:** 33 departamentos (incluida Bogotá D. C.) y 1.122 subdivisiones: municipios,
  áreas no municipalizadas e islas. Se incluyen todas porque también son lugares de nacimiento
  válidos en Colombia. Cada municipio trae `codigo` (5 dígitos, con el departamento en los dos
  primeros), `nombre` y el `codigo` de su `departamento`.

## Transformaciones

- Los nombres se pasan a mayúscula inicial (título español): las partículas `de`, `del`, `la`,
  `las`, `los`, `el`, `y`, `e`, `en` y `al` quedan en minúscula cuando no son la primera palabra.
- `BOGOTÁ, D.C.` se normaliza a `Bogotá D. C.`.
- No se corrigen nombres oficiales: por ejemplo, el municipio 76001 se llama `Santiago de Cali`
  en la DIVIPOLA.
- Si se actualiza el catálogo, cambia la fecha de descarga de este archivo y vuelve a correr los
  tests de `tests/test_lugares.py`.
