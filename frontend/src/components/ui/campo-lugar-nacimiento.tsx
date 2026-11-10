import { useId, useState } from "react";
import { useFormContext, type FieldValues, type Path } from "react-hook-form";
import { Combobox } from "./combobox";
import { FormField, FormItem } from "./form";
import { Icon } from "./icon";
import { Input } from "./input";
import {
  departamentoDeMunicipio,
  LUGAR_VACIO,
  opcionesDe,
  useDepartamentos,
  useMunicipios,
  usePaises,
  type LugarFormulario,
} from "@/lib/lugares";

type ErroresLugar = {
  message?: string;
  pais?: { message?: string };
  municipio?: { message?: string };
  ciudad?: { message?: string };
};

/** Mensajes del objeto y de sus campos; el backend los manda como `lugar_nacimiento.municipio`. */
function MensajesLugar({ error }: { error: ErroresLugar | undefined }) {
  if (!error) return null;
  const mensajes = [
    error.message,
    error.pais?.message,
    error.municipio?.message,
    error.ciudad?.message,
  ].filter((mensaje): mensaje is string => Boolean(mensaje));
  return (
    <>
      {[...new Set(mensajes)].map((mensaje) => (
        <div key={mensaje} role="alert" className="sta-field__msg">
          <Icon name="alert" />
          {mensaje}
        </div>
      ))}
    </>
  );
}

/** País y, si es Colombia, departamento y municipio de la DIVIPOLA; con otro país, una ciudad
 *  libre (HU-01, HU-07, HU-12). El departamento no se envía: se deriva del código del municipio. */
export function CampoLugarNacimiento<T extends FieldValues>({
  name,
  className,
}: {
  name: Path<T>;
  className?: string;
}) {
  const { control, watch } = useFormContext<T>();
  const paises = usePaises();
  const departamentos = useDepartamentos();
  const [departamentoElegido, setDepartamentoElegido] = useState("");
  const ids = {
    pais: useId(),
    paisEtiqueta: useId(),
    departamento: useId(),
    departamentoEtiqueta: useId(),
    municipio: useId(),
    municipioEtiqueta: useId(),
  };

  const lugar = (watch(name) as LugarFormulario | undefined) ?? LUGAR_VACIO;
  const esColombia = lugar.pais === "CO";
  const departamento = lugar.municipio
    ? departamentoDeMunicipio(lugar.municipio)
    : departamentoElegido;
  const municipios = useMunicipios(esColombia ? departamento : "");

  return (
    <FormField
      control={control}
      name={name}
      render={({ field, fieldState }) => {
        const error = fieldState.error as ErroresLugar | undefined;
        const valor = (field.value as LugarFormulario | undefined) ?? LUGAR_VACIO;

        return (
          <FormItem className={className}>
            <span className="sta-field__label">Lugar de nacimiento</span>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="sta-field">
                <span id={ids.paisEtiqueta} className="sta-field__label">
                  País
                </span>
                <Combobox
                  id={ids.pais}
                  aria-labelledby={ids.paisEtiqueta}
                  value={valor.pais}
                  onChange={(pais) => {
                    setDepartamentoElegido("");
                    field.onChange({ pais, municipio: null, ciudad: null });
                  }}
                  opciones={opcionesDe(paises.data)}
                  placeholder="Elige el país"
                  cargando={paises.isPending}
                  invalido={Boolean(error?.pais)}
                />
              </div>

              {esColombia ? (
                <>
                  <div className="sta-field">
                    <span id={ids.departamentoEtiqueta} className="sta-field__label">
                      Departamento
                    </span>
                    <Combobox
                      id={ids.departamento}
                      aria-labelledby={ids.departamentoEtiqueta}
                      value={departamento}
                      onChange={(codigo) => {
                        setDepartamentoElegido(codigo);
                        field.onChange({ pais: "CO", municipio: null, ciudad: null });
                      }}
                      opciones={opcionesDe(departamentos.data)}
                      placeholder="Elige el departamento"
                      cargando={departamentos.isPending}
                    />
                  </div>

                  <div className="sta-field">
                    <span id={ids.municipioEtiqueta} className="sta-field__label">
                      Municipio
                    </span>
                    <Combobox
                      id={ids.municipio}
                      aria-labelledby={ids.municipioEtiqueta}
                      value={valor.municipio ?? ""}
                      onChange={(codigo) => {
                        setDepartamentoElegido("");
                        field.onChange({ pais: "CO", municipio: codigo, ciudad: null });
                      }}
                      opciones={opcionesDe(municipios.data)}
                      placeholder={departamento ? "Elige el municipio" : "Elige el departamento"}
                      vacio="Sin municipios."
                      cargando={municipios.isPending}
                      disabled={!departamento}
                      invalido={Boolean(error?.municipio)}
                    />
                  </div>
                </>
              ) : (
                <label className="sta-field sm:col-span-2">
                  <span className="sta-field__label">Ciudad</span>
                  <Input
                    value={valor.ciudad ?? ""}
                    onChange={(evento) =>
                      field.onChange({
                        pais: valor.pais,
                        municipio: null,
                        ciudad: evento.target.value,
                      })
                    }
                    placeholder={
                      valor.pais ? "Escribe la ciudad de nacimiento" : "Elige primero el país"
                    }
                    disabled={!valor.pais}
                    aria-invalid={Boolean(error?.ciudad) || undefined}
                  />
                </label>
              )}
            </div>
            <MensajesLugar error={error} />
          </FormItem>
        );
      }}
    />
  );
}
