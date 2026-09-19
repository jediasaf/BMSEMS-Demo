import type { Config } from 'tailwindcss';

/**
 * EcoTwin design tokens.
 *
 * The palette is built for a control room: near-black backgrounds so an
 * operator's eye goes to the data, one accent reserved for "the system is
 * working", and status colours that keep their meaning everywhere. Status
 * colour is never the only carrier of meaning — every pill also has a label.
 */
const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './features/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        base: {
          900: '#05070a', // page
          850: '#080b11',
          800: '#0b1017', // panel
          750: '#0e141d',
          700: '#131b26', // raised
          600: '#1b2532', // border-strong
          500: '#26323f',
          400: '#3a4655',
        },
        ink: {
          100: '#e8eef5',
          200: '#c3cede',
          300: '#94a3b8',
          400: '#6b7a8d',
          500: '#4c5768',
        },
        accent: {
          DEFAULT: '#00e08a',
          soft: '#16fba0',
          dim: '#0b7a4d',
          wash: 'rgba(0, 224, 138, 0.10)',
        },
        teal: { DEFAULT: '#0fb9b1', dim: '#0a6b66' },
        status: {
          normal: '#22c55e',
          warning: '#f5a524',
          critical: '#f4404b',
          info: '#3b9dfb',
          idle: '#64748b',
        },
        prov: {
          measured: '#22c55e',
          predicted: '#3b9dfb',
          simulated: '#a78bfa',
          optimised: '#00e08a',
          derived: '#f5a524',
          injected: '#f472b6',
        },
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '0.875rem', letterSpacing: '0.02em' }],
      },
      borderRadius: { panel: '4px', pill: '3px' },
      boxShadow: {
        panel: '0 1px 0 rgba(255,255,255,0.03) inset, 0 8px 24px -16px rgba(0,0,0,0.9)',
        glow: '0 0 0 1px rgba(0,224,138,0.35), 0 0 22px -6px rgba(0,224,138,0.35)',
      },
      keyframes: {
        pulseDot: { '0%,100%': { opacity: '1' }, '50%': { opacity: '0.35' } },
        sweep: { '0%': { transform: 'translateX(-100%)' }, '100%': { transform: 'translateX(300%)' } },
      },
      animation: {
        'pulse-dot': 'pulseDot 2.2s ease-in-out infinite',
        sweep: 'sweep 1.8s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};

export default config;
