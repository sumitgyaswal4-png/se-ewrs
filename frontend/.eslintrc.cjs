module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true },
  extends: [
    'eslint:recommended',
    'plugin:react/recommended',
    'plugin:react/jsx-runtime',      // the new JSX transform: no React import needed
    'plugin:react-hooks/recommended',
  ],
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
  },
  settings: { react: { version: '18.3' } },
  plugins: ['react', 'react-hooks'],
  ignorePatterns: ['dist', 'node_modules', '*.config.js', '.eslintrc.cjs'],
  rules: {
    'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    // Prop validation is handled by the backend's response schemas plus
    // the typed endpoint layer; PropTypes would duplicate it.
    'react/prop-types': 'off',
  },
  overrides: [
    {
      files: ['**/*.test.{js,jsx}', 'src/test/**'],
      globals: {
        describe: 'readonly', it: 'readonly', expect: 'readonly',
        vi: 'readonly', beforeEach: 'readonly', afterEach: 'readonly',
        beforeAll: 'readonly', afterAll: 'readonly', global: 'writable',
      },
    },
  ],
}
