// Genera tokens.css a partir de tokens.json. Sin dependencias: solo Node.
// Uso: node build-tokens.mjs          escribe tokens.css
//      node build-tokens.mjs --check  falla si tokens.css no está al día
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const tokens = JSON.parse(readFileSync(join(here, "tokens.json"), "utf8"));
const target = join(here, "tokens.css");

// "{invert}" es un alias de otro token: se convierte en var(--invert).
const resolve = (value) => {
  const alias = /^\{([a-z0-9-]+)\}$/.exec(value);
  return alias ? `var(--${alias[1]})` : value;
};

const themeBlock = (theme, index) => {
  const selector = index === 0 ? `:root, [data-theme="${theme.id}"]` : `[data-theme="${theme.id}"]`;
  const lines = [...tokens.color.tokens, ...tokens.shadow.tokens].map(
    (t) => `  --${t.name}: ${resolve(t.value[theme.id])};`,
  );
  return [`${selector} {`, ...lines, "}"];
};

const scaleBlock = () => {
  const lines = [...tokens.spacing.tokens, ...tokens.radius.tokens, ...tokens.blur.tokens].map(
    (t) => `  --${t.name}: ${t.value};`,
  );
  for (const [name, stack] of Object.entries(tokens.type.families)) {
    lines.push(`  --font-${name}: ${stack};`);
  }
  return [":root {", ...lines, "}"];
};

const textClasses = () =>
  tokens.type.groups.flatMap((group) =>
    group.styles.map((s) => {
      const decl = [
        `font-family: var(--font-${group.family});`,
        `font-size: ${s.fontSize};`,
        `line-height: ${s.lineHeight};`,
        `font-weight: ${s.fontWeight};`,
      ];
      if (s.letterSpacing) decl.push(`letter-spacing: ${s.letterSpacing};`);
      return `.${s.name} { ${decl.join(" ")} }`;
    }),
  );

const fontFaces = () =>
  tokens.type.fonts.map(
    (f) =>
      `@font-face { font-family: "${f.family}"; src: url("${f.file}") format("woff2"); ` +
      `font-weight: ${f.weight}; font-style: ${f.style}; font-display: swap; }`,
  );

const css =
  [
    `/* ${tokens.name} — generado desde tokens.json. No editar a mano: cambie tokens.json y regenere. */`,
    ...tokens.color.themes.flatMap(themeBlock),
    ...scaleBlock(),
    ...textClasses(),
    ...fontFaces(),
  ].join("\n") + "\n";

if (process.argv.includes("--check")) {
  if (readFileSync(target, "utf8") !== css) {
    console.error("tokens.css no coincide con tokens.json. Ejecuta: npm run tokens");
    process.exit(1);
  }
} else {
  writeFileSync(target, css);
}
