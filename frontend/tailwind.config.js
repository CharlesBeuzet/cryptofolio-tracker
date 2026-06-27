/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        'crypto-green': '#00ff88',
        'crypto-red': '#ff4444',
        'crypto-bg': '#0a0e27',
        'crypto-card': '#141b2d',
        'crypto-border': '#1e293b',
        sillage: {
          green: 'var(--green)',
          down: 'var(--down)',
          accent: 'var(--accent)',
          ink: 'var(--ink)',
          soft: 'var(--soft)',
          card: 'var(--card)',
          card2: 'var(--card2)',
          line: 'var(--line)',
          gsoft: 'var(--gsoft)',
        },
      },
      fontFamily: {
        serif: ['Spectral', 'Georgia', 'serif'],
        mono: ['IBM Plex Mono', 'ui-monospace', 'monospace'],
      },
      borderRadius: {
        panel: '10px',
      },
    },
  },
  plugins: [],
}
