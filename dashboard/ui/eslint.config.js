import js from '@eslint/js'
import ts from 'typescript-eslint'
import svelte from 'eslint-plugin-svelte'

export default [
  js.configs.recommended,
  ...ts.configs.recommended,
  ...svelte.configs['flat/recommended'],
  {
    files: ['**/*.svelte'],
    languageOptions: {
      parserOptions: {
        parser: ts.parser,
      },
    },
  },
  {
    // TypeScript already enforces undefined checks — no-undef is redundant and
    // produces false positives for browser globals (SVGSVGElement, WebSocket, etc.)
    // no-useless-assignment has false positives for Svelte reactive statements
    // ($:) where variables persist across re-runs.
    files: ['**/*.ts', '**/*.svelte'],
    rules: {
      'no-undef': 'off',
      'no-useless-assignment': 'off',
    },
  },
  {
    ignores: ['dist/', 'node_modules/'],
  },
]
