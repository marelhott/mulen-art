import js from "@eslint/js";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

const shared = {
  ecmaVersion: 2022,
  sourceType: "module",
  parserOptions: { ecmaFeatures: { jsx: true } },
};

// Catches undefined identifiers, unused imports and hook mistakes; the build alone does not.
export default [
  js.configs.recommended,
  {
    // Browser code must not see Node globals (process, Buffer, require ...).
    files: ["frontend/src/**/*.{js,jsx}"],
    ignores: ["frontend/src/**/*.test.js"],
    languageOptions: { ...shared, globals: { ...globals.browser } },
    plugins: { react, "react-hooks": reactHooks },
    rules: {
      "react/jsx-no-undef": "error",
      "react/jsx-uses-vars": "error",
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "off",
      "no-unused-vars": ["warn", { args: "none", varsIgnorePattern: "^React$" }],
    },
  },
  {
    files: ["frontend/src/**/*.test.js"],
    languageOptions: { ...shared, globals: { ...globals.node } },
    rules: { "no-unused-vars": ["warn", { args: "none" }] },
  },
  {
    // The service worker runs in its own scope (self, caches, clients ...), not in a page.
    files: ["frontend/public/sw.js"],
    languageOptions: { ...shared, sourceType: "script", globals: { ...globals.serviceworker } },
    rules: { "no-unused-vars": ["warn", { args: "none" }] },
  },
];
