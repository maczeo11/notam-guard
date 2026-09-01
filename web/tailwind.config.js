/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html","./src/**/*.{ts,tsx}"],
  theme: { extend: { colors: { slate: {950: "#020617"}, amber: {500: "#f59e0b"}, cyan: {500: "#06b6d4"} } } },
  plugins: []
}
