export default [
  {
    ignores: ["dist/**", "node_modules/**", "*.config.js", "*.d.ts"],
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    rules: {
      "no-unused-vars": "off",
      "no-console": ["warn", { allow: ["warn", "error"] }],
      "prefer-const": "error",
      "no-var": "error",
      "eqeqeq": ["error", "always"],
    },
  },
];
