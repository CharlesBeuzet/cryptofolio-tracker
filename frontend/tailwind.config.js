/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'crypto-green': '#00ff88',
        'crypto-red': '#ff4444',
        'crypto-bg': '#0a0e27',
        'crypto-card': '#141b2d',
        'crypto-border': '#1e293b',
      },
    },
  },
  plugins: [],
}

