import react from "eslint-plugin-react";
import globals from "globals";

// Catches undefined identifiers and unused imports; the build alone does not.
export default [
  {
    files: ["frontend/src/**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { ...globals.browser, ...globals.node },
    },
    plugins: { react },
    rules: {
      "no-undef": "error",
      "react/jsx-no-undef": "error",
      "react/jsx-uses-vars": "error",
      "no-unused-vars": ["warn", { args: "none", varsIgnorePattern: "^React$" }],
    },
  },
];
