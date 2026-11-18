// Prueba de carga de la búsqueda de vuelos (RNF-01, issue #135).
//
// 100 usuarios virtuales (la mitad con sesión de cliente) buscan vuelos y regresos durante 10 minutos
// contra la base `sta_carga` sembrada por backend/scripts/carga/sembrar.py. Los umbrales de
// RNF-01 (p95 <= 2 s, p99 <= 4 s, errores < 1 %) se miden solo en la meseta, no en la rampa.
//
// Uso (docs/pruebas/carga-busqueda.md):
//   docker compose --profile carga run --rm k6
//   docker compose --profile carga run --rm k6 run -e RAMPA=10s -e DURACION=30s /carga/busqueda.js
//
// Variables (-e CLAVE=valor): BASE_URL, VUS, RAMPA, DURACION, PAUSA_S, CLIENTES, CARGA_CONTRASENA.
// Código de salida 99: falló un umbral (es el resultado de la prueba, no un error del script).
import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';
import { Counter, Rate } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://backend-carga:8000/api/v1';
const VUS = parseInt(__ENV.VUS || '100', 10);
const RAMPA = __ENV.RAMPA || '1m';
const DURACION = __ENV.DURACION || '10m';
const PAUSA_S = parseFloat(__ENV.PAUSA_S || '1');
const CLIENTES = parseInt(__ENV.CLIENTES || '100', 10);
const CONTRASENA = __ENV.CARGA_CONTRASENA || 'CargaSta2026';

const UNIDADES_MS = { ms: 1, s: 1000, m: 60000, h: 3600000 };

function aMs(texto) {
  const partes = /^(\d+)(ms|s|m|h)$/.exec(texto);
  if (!partes) {
    throw new Error('Duración no válida: ' + texto + ' (use 30s, 1m, 10m)');
  }
  return parseInt(partes[1], 10) * UNIDADES_MS[partes[2]];
}

const RAMPA_MS = aMs(RAMPA);
const DURACION_MS = aMs(DURACION);

const COMBOS = [
  'sin_filtros',
  'origen',
  'origen_destino',
  'origen_semana',
  'precio_clase',
  'internacional_quincena',
  'destino_primera_precio',
  'origen_franja_duracion',
  'nacional_duracion_mes',
  'codigo',
  'ida_exacta',
];
// `ida_exacta` solo se usa en el paso de regreso: la búsqueda de la ida elegida.
const COMBOS_DEL_PASO_A = COMBOS.slice(0, 10);
const ORDENES = ['precio', 'fecha', 'duracion'];
const CLASES = ['economica', 'primera'];
const NACIONALES = ['BOG', 'MDE', 'CLO', 'CTG', 'BAQ', 'PEI', 'BGA', 'SMR', 'ADZ', 'CUC'];
const HABILITADAS = ['BOG', 'MDE', 'CLO', 'CTG', 'PEI'];
const EXTRANJERAS = ['MAD', 'LHR', 'JFK', 'EZE', 'MIA'];
const FRANJAS = [
  ['00:00', '05:59'],
  ['06:00', '11:59'],
  ['12:00', '17:59'],
  ['18:00', '23:59'],
];
// Rutas con buenas posibilidades de tener vuelos de regreso en la ventana sembrada.
const RUTAS_DE_IDA = [
  ['PEI', 'BOG'],
  ['BOG', 'MDE'],
  ['BOG', 'CTG'],
  ['MDE', 'BOG'],
  ['CLO', 'BOG'],
  ['BAQ', 'BOG'],
  ['BOG', 'ADZ'],
  ['BOG', 'MIA'],
  ['PEI', 'JFK'],
  ['BOG', 'MAD'],
  ['CTG', 'MIA'],
  ['MDE', 'MIA'],
];

const MS_DIA = 24 * 3600 * 1000;
const MS_BOGOTA = 5 * 3600 * 1000; // UTC-5, sin horario de verano
const HOY_MS = Date.now();

const busquedasRegistrables = new Counter('busquedas_registrables');
const regresosConResultados = new Rate('regresos_con_resultados');

// Los umbrales miran solo la meseta; la rampa y la bajada se miden pero no cuentan.
const thresholds = {
  'http_req_duration{endpoint:vuelos,fase:meseta}': ['p(95)<2000', 'p(99)<4000'],
  'http_req_duration{endpoint:regresos,fase:meseta}': ['p(95)<2000', 'p(99)<4000'],
  'http_req_failed{fase:meseta}': ['rate<0.01'],
  checks: ['rate>0.99'],
  // Solo para que salgan en el resumen: no fallan nunca.
  'http_req_duration{fase:meseta}': ['max>=0'],
  'http_reqs{fase:meseta}': ['count>=0'],
  'http_req_duration{endpoint:login}': ['max>=0'],
};
for (const sesion of ['cliente', 'visitante']) {
  thresholds['http_req_duration{endpoint:vuelos,fase:meseta,sesion:' + sesion + '}'] = ['p(95)<2000'];
  thresholds['http_req_duration{endpoint:regresos,fase:meseta,sesion:' + sesion + '}'] = [
    'p(95)<2000',
  ];
}
for (const orden of ORDENES) {
  thresholds['http_req_duration{endpoint:vuelos,fase:meseta,orden:' + orden + '}'] = ['p(95)<2000'];
  thresholds['http_req_duration{endpoint:regresos,fase:meseta,orden:' + orden + '}'] = [
    'p(95)<2000',
  ];
}
for (const combo of COMBOS) {
  thresholds['http_req_duration{endpoint:vuelos,fase:meseta,combo:' + combo + '}'] = ['p(95)<2000'];
}

export const options = {
  scenarios: {
    busqueda: {
      executor: 'ramping-vus',
      startVUs: 0,
      gracefulRampDown: '30s',
      stages: [
        { duration: RAMPA, target: VUS },
        { duration: DURACION, target: VUS },
        { duration: '30s', target: 0 },
      ],
    },
  },
  // La cookie de sesión debe sobrevivir entre iteraciones del mismo usuario virtual.
  noCookiesReset: true,
  setupTimeout: '2m',
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max', 'count'],
  thresholds: thresholds,
};

// ---------- Utilidades ----------

function aleatorio(lista) {
  return lista[Math.floor(Math.random() * lista.length)];
}

function entre(minimo, maximo) {
  return minimo + Math.floor(Math.random() * (maximo - minimo + 1));
}

function distinto(lista, excluido) {
  let valor = aleatorio(lista);
  while (valor === excluido) {
    valor = aleatorio(lista);
  }
  return valor;
}

function pad3(numero) {
  return ('00' + numero).slice(-3);
}

function fechaBogota(ms) {
  return new Date(ms - MS_BOGOTA).toISOString().slice(0, 10);
}

function fechaMas(dias) {
  return fechaBogota(HOY_MS + dias * MS_DIA);
}

function cadena(parametros) {
  return Object.keys(parametros)
    .map(function (clave) {
      return encodeURIComponent(clave) + '=' + encodeURIComponent(parametros[clave]);
    })
    .join('&');
}

function pausa() {
  sleep(PAUSA_S * (0.5 + Math.random()));
}

function fase() {
  const transcurrido = Date.now() - exec.scenario.startTime;
  if (transcurrido < RAMPA_MS) {
    return 'rampa';
  }
  return transcurrido < RAMPA_MS + DURACION_MS ? 'meseta' : 'bajada';
}

// Un usuario virtual con número par es cliente (50 %); el resto busca como visitante.
const ES_CLIENTE = __VU % 2 === 0;
let sesionIniciada = false;

// ---------- Combinaciones de filtros (ninguna da 422) ----------

function combinacion(nombre) {
  switch (nombre) {
    case 'sin_filtros':
      return {};
    case 'origen':
      return { origen: aleatorio(NACIONALES) };
    case 'origen_destino': {
      const origen = aleatorio(NACIONALES);
      return { origen: origen, destino: distinto(NACIONALES, origen) };
    }
    case 'origen_semana': {
      const dia = entre(2, 85);
      return { origen: aleatorio(NACIONALES), fecha_desde: fechaMas(dia), fecha_hasta: fechaMas(dia + 7) };
    }
    case 'precio_clase':
      // El ejemplo de HU-20 (entre 200.000 y 400.000 en económica) con variantes de 50.000.
      return {
        origen: aleatorio(NACIONALES),
        precio_min: 200000 + aleatorio([-50000, 0, 50000]),
        precio_max: 400000 + aleatorio([-50000, 0, 50000]),
        clase: 'economica',
      };
    case 'internacional_quincena': {
      const dia = entre(2, 77);
      return { tipo: 'internacional', fecha_desde: fechaMas(dia), fecha_hasta: fechaMas(dia + 14) };
    }
    case 'destino_primera_precio':
      return { destino: aleatorio(EXTRANJERAS), clase: 'primera', precio_max: 9000000 };
    case 'origen_franja_duracion': {
      const franja = aleatorio(FRANJAS);
      return {
        origen: aleatorio(NACIONALES),
        hora_desde: franja[0],
        hora_hasta: franja[1],
        duracion_max: 90,
      };
    }
    case 'nacional_duracion_mes': {
      const dia = entre(2, 62);
      return {
        tipo: 'nacional',
        duracion_min: 60,
        duracion_max: 120,
        fecha_desde: fechaMas(dia),
        fecha_hasta: fechaMas(dia + 30),
      };
    }
    case 'codigo':
      return { codigo: 'STA-0' + pad3(entre(0, 99)).slice(-2) };
    default:
      throw new Error('Combinación desconocida: ' + nombre);
  }
}

// ---------- Peticiones ----------

function pedir(ruta, parametros, etiquetas) {
  const url = BASE_URL + ruta + (parametros ? '?' + cadena(parametros) : '');
  const todas = Object.assign({ fase: fase(), name: 'GET ' + ruta }, etiquetas);
  return http.get(url, { tags: todas });
}

// Búsqueda de vuelos o de regresos con las comprobaciones de siempre y el conteo de las que el
// servidor debe registrar (RF-29: la primera página de un cliente con sesión).
function buscar(endpoint, ruta, parametros, extra) {
  const sesion = ES_CLIENTE ? 'cliente' : 'visitante';
  const etiquetas = Object.assign(
    { endpoint: endpoint, orden: parametros.orden, sesion: sesion, pagina: String(parametros.pagina) },
    extra,
  );
  const respuesta = pedir(ruta, parametros, etiquetas);
  let cuerpo = null;
  check(respuesta, {
    'status 200': function (r) {
      return r.status === 200;
    },
    'items es una lista': function (r) {
      try {
        cuerpo = r.json();
        return Array.isArray(cuerpo.items);
      } catch (e) {
        return false;
      }
    },
  });
  if (respuesta.status === 200 && ES_CLIENTE && parametros.pagina === 1) {
    busquedasRegistrables.add(1);
  }
  return cuerpo;
}

function iniciarSesion() {
  const usuario = 'carga_cliente_' + pad3(((__VU - 1) % CLIENTES) + 1);
  const etiquetas = { endpoint: 'login', fase: fase() };
  const login = http.post(
    BASE_URL + '/auth/login',
    JSON.stringify({ usuario: usuario, contrasena: CONTRASENA }),
    {
      headers: { 'Content-Type': 'application/json' },
      tags: Object.assign({ name: 'POST /auth/login' }, etiquetas),
    },
  );
  const entro = check(login, {
    'login 200': function (r) {
      return r.status === 200;
    },
    'login deja la cookie sta_sesion': function (r) {
      return !!r.cookies.sta_sesion && r.cookies.sta_sesion.length > 0;
    },
  });
  if (!entro) {
    // RNF-13 bloquea la cuenta 15 minutos tras 5 intentos fallidos: no se reintenta.
    exec.test.abort('Falló el login de ' + usuario + ' (' + login.status + '): ' + login.body);
  }
  const yo = http.get(BASE_URL + '/auth/me', {
    tags: Object.assign({ name: 'GET /auth/me' }, etiquetas),
  });
  const conSesion = check(yo, {
    'la sesión sirve en /auth/me': function (r) {
      return r.status === 200;
    },
  });
  if (!conSesion) {
    exec.test.abort(
      'La cookie de sesión no viaja de vuelta (' + yo.status + '): ¿COOKIE_SECURE=false en backend-carga?',
    );
  }
}

// ---------- Preparación: idas candidatas para el paso de regreso ----------

export function setup() {
  const etiquetas = { endpoint: 'setup', fase: 'setup' };
  const ciudades = http.get(BASE_URL + '/ciudades', {
    tags: Object.assign({ name: 'GET /ciudades' }, etiquetas),
  });
  if (ciudades.status !== 200 || ciudades.json().length < 37) {
    exec.test.abort('GET /ciudades no responde el catálogo (' + ciudades.status + ').');
  }

  const idas = [];
  for (const ruta of RUTAS_DE_IDA) {
    const respuesta = http.get(
      BASE_URL +
        '/busqueda/vuelos?' +
        cadena({ origen: ruta[0], destino: ruta[1], orden: 'fecha', por_pagina: 100 }),
      { tags: Object.assign({ name: 'GET /busqueda/vuelos' }, etiquetas) },
    );
    if (respuesta.status !== 200) {
      exec.test.abort('Falló la búsqueda de idas ' + ruta.join('-') + ': ' + respuesta.status);
    }
    for (const vuelo of respuesta.json().items) {
      idas.push({
        id: vuelo.id,
        origen: vuelo.origen.codigo,
        destino: vuelo.destino.codigo,
        tipo: vuelo.tipo,
        salida: vuelo.salida,
        llegada: vuelo.llegada,
      });
    }
  }
  if (idas.length === 0) {
    exec.test.abort('Sin vuelos: ¿corriste el sembrado?');
  }
  return { idas: idas };
}

// ---------- Iteración de cada usuario virtual ----------

// Ciudad de regreso: casi siempre el origen de la ida; a veces otra ciudad que RF-14 permita.
function ciudadDeRegreso(ida) {
  if (Math.random() < 0.7) {
    return ida.origen;
  }
  if (ida.tipo === 'internacional') {
    return distinto(HABILITADAS, ida.origen);
  }
  return distinto(NACIONALES, ida.destino);
}

function regreso(data) {
  const ida = aleatorio(data.idas);
  // La ida elegida, buscada por su día de salida exacto (hora de Bogotá, el origen de las idas).
  const dia = fechaBogota(Date.parse(ida.salida));
  buscar(
    'vuelos',
    '/busqueda/vuelos',
    {
      origen: ida.origen,
      destino: ida.destino,
      fecha_desde: dia,
      fecha_hasta: dia,
      orden: aleatorio(ORDENES),
      pagina: 1,
    },
    { combo: 'ida_exacta' },
  );
  pausa();

  const parametros = {
    vuelo_ida_id: ida.id,
    destino: ciudadDeRegreso(ida),
    fecha: new Date(Date.parse(ida.llegada) + entre(1, 7) * MS_DIA).toISOString().slice(0, 10),
    orden: aleatorio(ORDENES),
    pagina: 1,
  };
  if (Math.random() < 0.3) {
    parametros.clase = aleatorio(CLASES);
  }
  const cuerpo = buscar('regresos', '/busqueda/regresos', parametros, {});
  if (cuerpo !== null) {
    regresosConResultados.add(cuerpo.total > 0);
  }
  pausa();
}

export default function (data) {
  if (ES_CLIENTE && !sesionIniciada) {
    iniciarSesion();
    sesionIniciada = true;
  }

  // Paso A (siempre): una búsqueda de vuelos, orden al azar, primera página.
  const combo = aleatorio(COMBOS_DEL_PASO_A);
  const busqueda = Object.assign({}, combinacion(combo), { orden: aleatorio(ORDENES), pagina: 1 });
  buscar('vuelos', '/busqueda/vuelos', busqueda, { combo: combo });
  pausa();

  // Paso B (25 %): la misma búsqueda en la segunda página.
  if (Math.random() < 0.25) {
    buscar('vuelos', '/busqueda/vuelos', Object.assign({}, busqueda, { pagina: 2 }), { combo: combo });
    pausa();
  }

  // Paso C (35 %): elige una ida y busca su regreso.
  if (Math.random() < 0.35) {
    regreso(data);
  }
}

// ---------- Resumen en Markdown ----------

function etiquetasDe(nombre) {
  const partes = /^[^{]+\{(.*)\}$/.exec(nombre);
  if (!partes) {
    return null;
  }
  const etiquetas = {};
  partes[1].split(',').forEach(function (par) {
    const i = par.indexOf(':');
    etiquetas[par.slice(0, i)] = par.slice(i + 1);
  });
  return etiquetas;
}

function dec(valor) {
  return typeof valor === 'number' && isFinite(valor) ? valor.toFixed(1) : '-';
}

// ✅ / ❌ según los umbrales reales de la métrica; "informativo" si solo tiene los de relleno.
function veredicto(metrica) {
  const umbrales = metrica.thresholds || {};
  const reales = Object.keys(umbrales).filter(function (expresion) {
    return expresion !== 'max>=0' && expresion !== 'count>=0';
  });
  if (reales.length === 0) {
    return 'informativo';
  }
  const fallan = reales.filter(function (expresion) {
    return !umbrales[expresion].ok;
  });
  return fallan.length === 0 ? '✅' : '❌ ' + fallan.join(', ');
}

function filaDeTendencia(rotulo, metrica) {
  const v = metrica.values;
  return (
    '| ' + rotulo + ' | ' + v.count + ' | ' + dec(v.med) + ' | ' + dec(v['p(90)']) + ' | ' +
    dec(v['p(95)']) + ' | ' + dec(v['p(99)']) + ' | ' + dec(v.max) + ' | ' + veredicto(metrica) + ' |'
  );
}

const ENCABEZADO =
  '| Métrica | Peticiones | p50 | p90 | p95 | p99 | máx | Umbral |\n' +
  '|---|---:|---:|---:|---:|---:|---:|---|';

// Una tabla con las submétricas de http_req_duration cuyas etiquetas cumple `acepta`.
function tabla(titulo, data, acepta, rotular) {
  const filas = [];
  Object.keys(data.metrics)
    .filter(function (nombre) {
      return nombre.indexOf('http_req_duration{') === 0;
    })
    .sort()
    .forEach(function (nombre) {
      const etiquetas = etiquetasDe(nombre);
      if (etiquetas && acepta(etiquetas)) {
        filas.push(filaDeTendencia(rotular(etiquetas), data.metrics[nombre]));
      }
    });
  if (filas.length === 0) {
    return '';
  }
  return '### ' + titulo + ' (ms)\n\n' + ENCABEZADO + '\n' + filas.join('\n') + '\n\n';
}

function resumenMarkdown(data) {
  const m = data.metrics;
  const meseta = m['http_reqs{fase:meseta}'];
  const fallidas = m['http_req_failed{fase:meseta}'];
  const peticiones = meseta ? meseta.values.count : 0;
  const segundos = DURACION_MS / 1000;
  let md = '## Resumen de la meseta\n\n';
  md += '- Duración total de la corrida: ' + (data.state.testRunDurationMs / 1000).toFixed(1) + ' s ';
  md += '(rampa ' + RAMPA + ', meseta ' + DURACION + ', bajada 30s), ' + VUS + ' usuarios virtuales como máximo.\n';
  md += '- Peticiones en la meseta: ' + peticiones + ' (' + (peticiones / segundos).toFixed(1) + ' por segundo).\n';
  if (fallidas) {
    md += '- Peticiones fallidas en la meseta: ' + fallidas.values.passes + ' de ' +
      (fallidas.values.passes + fallidas.values.fails) + ' (' +
      (fallidas.values.rate * 100).toFixed(3) + ' %) ' + veredicto(fallidas) + '.\n';
  }
  md += '- Peticiones de toda la corrida: ' + m.http_reqs.values.count + ' (' + dec(m.http_reqs.values.rate) + ' por segundo).\n';
  md += '- Iteraciones: ' + m.iterations.values.count + '. Máximo de usuarios virtuales: ' + m.vus_max.values.max + '.\n';
  md += '- Comprobaciones (status 200, items es lista, login, sesión): ' +
    (m.checks.values.rate * 100).toFixed(3) + ' % ' + veredicto(m.checks) + '.\n';
  if (m.busquedas_registrables) {
    md += '- busquedas_registrables (primera página de un cliente con respuesta 200): ' +
      m.busquedas_registrables.values.count + '.\n';
  }
  if (m.regresos_con_resultados) {
    md += '- Regresos con al menos un resultado: ' +
      (m.regresos_con_resultados.values.rate * 100).toFixed(1) + ' %.\n';
  }
  md += '\n';

  md += tabla('Por endpoint, meseta', data,
    function (e) { return e.fase === 'meseta' && Object.keys(e).length <= 2; },
    function (e) { return e.endpoint ? '`' + e.endpoint + '`' : 'todas las peticiones'; });
  md += tabla('Por orden, meseta', data,
    function (e) { return e.fase === 'meseta' && e.orden !== undefined; },
    function (e) { return '`' + e.endpoint + '` orden=' + e.orden; });
  md += tabla('Por sesión, meseta', data,
    function (e) { return e.fase === 'meseta' && e.sesion !== undefined; },
    function (e) { return '`' + e.endpoint + '` ' + e.sesion; });
  md += tabla('Por combinación de filtros de `vuelos`, meseta', data,
    function (e) { return e.fase === 'meseta' && e.combo !== undefined; },
    function (e) { return '`' + e.combo + '`'; });
  md += tabla('Login (informativo, toda la corrida)', data,
    function (e) { return e.endpoint === 'login'; },
    function () { return '`POST /auth/login` y `GET /auth/me`'; });

  md += '### Umbrales\n\n| Métrica | Umbral | Resultado |\n|---|---|---|\n';
  Object.keys(m).sort().forEach(function (nombre) {
    const umbrales = m[nombre].thresholds || {};
    Object.keys(umbrales).forEach(function (expresion) {
      if (expresion === 'max>=0' || expresion === 'count>=0') {
        return;
      }
      md += '| `' + nombre + '` | `' + expresion + '` | ' + (umbrales[expresion].ok ? '✅' : '❌') + ' |\n';
    });
  });
  return md;
}

export function handleSummary(data) {
  const md = resumenMarkdown(data);
  return {
    stdout: md,
    '/resultados/resumen.md': md,
    '/resultados/resumen.json': JSON.stringify(data, null, 2),
  };
}
