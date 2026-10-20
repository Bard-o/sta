// Cálculos de hora para la API simulada. El backend real usa tzdata (RF-15); aquí basta Intl.

/** Desfase de la zona IANA frente a UTC, en minutos, en ese instante (con horario de verano). */
export function desfaseMinutos(zona: string, instante: Date): number {
  const nombre =
    new Intl.DateTimeFormat("en-US", { timeZone: zona, timeZoneName: "longOffset" })
      .formatToParts(instante)
      .find((p) => p.type === "timeZoneName")?.value ?? "GMT";
  const m = /GMT([+-])(\d{2}):(\d{2})/.exec(nombre);
  if (!m) return 0;
  return (m[1] === "-" ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3]));
}

/** Fecha (aaaa-mm-dd) y hora (hh:mm) locales de una zona → instante UTC. */
export function localAUtc(fecha: string, hora: string, zona: string): Date {
  const [a, mes, d] = fecha.split("-").map(Number);
  const [h, min] = hora.split(":").map(Number);
  const comoSiFueraUtc = Date.UTC(a, mes - 1, d, h, min);
  // Dos pasadas: el desfase depende del instante, que a su vez depende del desfase.
  const aprox = comoSiFueraUtc - desfaseMinutos(zona, new Date(comoSiFueraUtc)) * 60_000;
  return new Date(comoSiFueraUtc - desfaseMinutos(zona, new Date(aprox)) * 60_000);
}

export function sumarMinutos(fecha: Date, minutos: number): Date {
  return new Date(fecha.getTime() + minutos * 60_000);
}

/** ISO 8601 en UTC sin milisegundos, como lo devuelve el backend. */
export function aIso(fecha: Date): string {
  return fecha.toISOString().replace(/\.\d{3}Z$/, "Z");
}

/** Días entre dos fechas aaaa-mm-dd, ambas incluidas. */
export function fechasEntre(desde: string, hasta: string): string[] {
  const fechas: string[] = [];
  for (let t = Date.parse(`${desde}T00:00:00Z`); t <= Date.parse(`${hasta}T00:00:00Z`);) {
    fechas.push(new Date(t).toISOString().slice(0, 10));
    t += 86_400_000;
  }
  return fechas;
}
