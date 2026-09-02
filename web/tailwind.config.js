/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      colors: {
        // Warm neutral ground, so the page does not read as default-Tailwind slate.
        ink: {
          950: '#0c0a09',
          900: '#131110',
          850: '#1a1817',
          800: '#232020',
          700: '#332e2c',
          500: '#7c736e',
          400: '#a49a94',
          200: '#e7e2df',
        },
      },
      keyframes: {
        rise: { '0%': { opacity: '0', transform: 'translateY(4px)' }, '100%': { opacity: '1', transform: 'none' } },
      },
      animation: { rise: 'rise 200ms ease-out both' },
    },
  },
  plugins: [],
}
