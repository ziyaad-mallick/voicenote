/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'media',
  content: ['./app/**/*.{js,jsx}', './components/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        mono: ["'IBM Plex Mono'", 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
};
