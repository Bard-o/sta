import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import { defineConfig, globalIgnores } from "eslint/config";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig([
  globalIgnores(["dist", "node_modules", "src/api/schema.d.ts"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat["recommended-latest"],
      reactRefresh.configs.vite,
      prettier,
    ],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    rules: {
      // DESIGN.md: nada de colores sueltos ni valores arbitrarios de Tailwind en las pantallas.
      "no-restricted-syntax": [
        "error",
        {
          selector: "Literal[value=/#[0-9a-fA-F]{3,8}\\b|rgba?\\(/]",
          message:
            "Usa un token de design/ (var(--…) o su utilidad de Tailwind), no un color suelto.",
        },
        {
          selector: "Literal[value=/\\b[a-z-]+-\\[[^\\]]+\\]/]",
          message: "Sin valores arbitrarios de Tailwind: usa la utilidad mapeada al token.",
        },
      ],
    },
  },
]);
