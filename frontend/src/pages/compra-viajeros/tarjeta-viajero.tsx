import { useFormContext, useWatch } from "react-hook-form";
import type { Schemas } from "@/api/client";
import { Button } from "@/components/ui/button";
import { CampoLista, CampoTexto } from "@/components/ui/campos";
import { Glass } from "@/components/ui/glass";
import { cop } from "@/lib/format";
import { edadEn, fechaMinimaNacimiento, GENEROS, hoy, TIPOS_DOCUMENTO } from "@/lib/persona";
import type { Clase, Entrada } from "./esquema";

type Perfil = Schemas["PerfilSalida"];
type Vuelo = Schemas["VueloDetalle"];

const NOMBRE_CLASE: Record<Clase, string> = { economica: "Económica", primera: "Primera clase" };

/** «Económica, $ 262.500» (o «agotada»): lo que cuesta cada clase en ese vuelo hoy. */
function opcionesDeClase(vuelo: Vuelo | undefined) {
  return (["economica", "primera"] as const).map((c) => {
    const datos = vuelo?.[c];
    const detalle = !datos ? "" : datos.agotada ? ", agotada" : `, ${cop(datos.precio_vigente)}`;
    return { value: c, label: `${NOMBRE_CLASE[c]}${detalle}` };
  });
}

/** Un viajero del formulario (HU-24, RF-31): sus datos, su contacto de emergencia y la clase de
 *  cada tramo (HU-26). «Soy yo» llena los datos desde el perfil del cliente. */
export function TarjetaViajero({
  indice,
  vuelos,
  fechasDeSalida,
  perfil,
}: {
  indice: number;
  /** Los vuelos de la selección, en el orden de los tramos. */
  vuelos: (Vuelo | undefined)[];
  /** Fecha local de salida de cada tramo (aaaa-mm-dd), para la edad el día del vuelo. */
  fechasDeSalida: string[];
  perfil: Perfil | undefined;
}) {
  const { setValue, control } = useFormContext<Entrada>();
  const nacimiento = useWatch({ control, name: `viajeros.${indice}.fecha_nacimiento` });
  const prefijo = `viajeros.${indice}` as const;
  const completo = vuelos.length === 2;

  const edad =
    nacimiento && /^\d{4}-\d{2}-\d{2}$/.test(nacimiento) && nacimiento <= hoy()
      ? edadEn(nacimiento, fechasDeSalida[0])
      : null;

  function soyYo() {
    if (!perfil) return;
    const ajustes = {
      tipo_documento: perfil.tipo_documento,
      numero_documento: perfil.numero_documento,
      nombres: perfil.nombres,
      apellidos: perfil.apellidos,
      fecha_nacimiento: perfil.fecha_nacimiento,
      genero: perfil.genero,
      email: perfil.email,
      telefono: perfil.telefono ?? "",
    } as const;
    for (const [campo, valor] of Object.entries(ajustes)) {
      setValue(`${prefijo}.${campo}` as `viajeros.${number}.nombres`, valor, {
        shouldDirty: true,
        shouldValidate: true,
      });
    }
  }

  return (
    <Glass
      as="fieldset"
      title={`Viajero ${indice + 1}`}
      aria-label={`Viajero ${indice + 1}`}
      actions={
        <Button size="sm" variant="secondary" disabled={!perfil} onClick={soyYo}>
          Soy yo: datos de mi perfil
          <span className="sr-only"> en el viajero {indice + 1}</span>
        </Button>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <CampoLista<Entrada>
          name={`${prefijo}.tipo_documento`}
          label="Tipo de documento"
          opciones={TIPOS_DOCUMENTO}
        />
        <CampoTexto<Entrada>
          name={`${prefijo}.numero_documento`}
          label="Número de documento"
          autoComplete="off"
        />
        <CampoLista<Entrada>
          name={`${prefijo}.genero`}
          label="Género"
          opciones={GENEROS}
          placeholder="Elige una opción"
        />
        <CampoTexto<Entrada> name={`${prefijo}.nombres`} label="Nombres" autoComplete="off" />
        <CampoTexto<Entrada> name={`${prefijo}.apellidos`} label="Apellidos" autoComplete="off" />
        <CampoTexto<Entrada>
          name={`${prefijo}.fecha_nacimiento`}
          label="Fecha de nacimiento"
          type="date"
          min={fechaMinimaNacimiento()}
          max={hoy()}
          ayuda={
            edad === null
              ? undefined
              : `Tendrá ${edad} ${edad === 1 ? "año" : "años"} el día del vuelo.`
          }
        />
        <CampoTexto<Entrada> name={`${prefijo}.telefono`} label="Teléfono" type="tel" />
        <CampoTexto<Entrada> name={`${prefijo}.email`} label="Correo" type="email" />
        <CampoTexto<Entrada>
          name={`${prefijo}.contacto_nombre`}
          label="Contacto de emergencia"
          autoComplete="off"
        />
        <CampoTexto<Entrada>
          name={`${prefijo}.contacto_telefono`}
          label="Teléfono del contacto"
          type="tel"
        />
        {vuelos.map((vuelo, tramo) => (
          <CampoLista<Entrada>
            key={tramo}
            name={`${prefijo}.clases.${tramo}`}
            label={completo ? (tramo === 0 ? "Clase de la ida" : "Clase del regreso") : "Clase"}
            opciones={opcionesDeClase(vuelo)}
          />
        ))}
      </div>
    </Glass>
  );
}
