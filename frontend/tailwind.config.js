import tailwindcssAnimate from 'tailwindcss-animate';

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        canvas: '#080B10',
        surface: {
          DEFAULT: '#0F172A',
          subtle: '#131D33',
        },
        card: {
          DEFAULT: '#1E293B',
          hover: '#334155',
        },
        border: {
          subdued: '#1E293B',
          DEFAULT: '#334155',
          highlight: '#475569',
        },
        brand: {
          50: '#F0F9FF',
          100: '#E0F2FE',
          400: '#38BDF8',
          500: '#3B82F6',
          600: '#2563EB',
        },
        trading: {
          profit: '#10B981',
          'profit-neon': '#00E676',
          loss: '#EF4444',
          'loss-neon': '#FF5252',
          warning: '#F59E0B',
          neutral: '#94A3B8',
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Roboto Mono', 'monospace'],
      },
      boxShadow: {
        'glow-profit': '0 0 15px -3px rgba(16, 185, 129, 0.35)',
        'glow-loss': '0 0 15px -3px rgba(239, 68, 68, 0.35)',
        'glow-brand': '0 0 15px -3px rgba(56, 189, 248, 0.35)',
        'glow-warning': '0 0 15px -3px rgba(245, 158, 11, 0.35)',
      },
      keyframes: {
        'pulse-glow': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
        'shimmer': {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        'pulse-glow': 'pulse-glow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'shimmer': 'shimmer 1.5s infinite',
      },
    },
  },
  plugins: [
    tailwindcssAnimate,
  ],
};
