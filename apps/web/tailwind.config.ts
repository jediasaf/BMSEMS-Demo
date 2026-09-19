import type { Config } from 'tailwindcss';

/**
 * EcoTwin design tokens.
 *
 * A control-room palette, not a SaaS one. The background is a deep green-black
 * so the accent reads as "this system is live" rather than as decoration, and
 * status colour keeps one meaning everywhere. Status is never the only carrier
 * of meaning: every pill also has a label, and every chart series a legend.
 */
const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './features/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Deep green-black. 950 is the page, 900 the chrome, 850/800 panels.
        base: {
          950: '#050c0b',
          900: '#07100f',
          850: '#0a1615',
          800: '#0c1a19',
          750: '#0f211f',
          700: '#132927',
          650: '#183330',
          600: '#1e3d39', // border-strong
          500: '#2a514c',
          400: '#3d6b64',
        },
        ink: {
          100: '#e6f0ee',
          200: '#bdcecb',
          300: '#8ba39f',
          400: '#728c88',
          500: '#4a615e',
          600: '#374a47',
        },
        accent: {
          DEFAULT: '#3ddc97',
          soft: '#6ef3b6',
          deep: '#1fae73',
          dim: '#0f7a52',
          wash: 'rgba(61, 220, 151, 0.10)',
        },
        info: { DEFAULT: '#4cc2ff', deep: '#1b7fb5' },
        status: {
          normal: '#3ddc97',
          warning: '#f2b544',
          critical: '#ff5a5f',
          info: '#4cc2ff',
          idle: '#5b7570',
        },
        prov: {
          measured: '#3ddc97',
          predicted: '#4cc2ff',
          simulated: '#a98bfa',
          optimised: '#22d3a6',
          derived: '#f2b544',
          injected: '#f472b6',
        },
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        '3xs': ['0.5938rem', { lineHeight: '0.75rem', letterSpacing: '0.06em' }],
        '2xs': ['0.6875rem', { lineHeight: '0.875rem', letterSpacing: '0.02em' }],
      },
      spacing: { sidebar: '232px', 'sidebar-compact': '56px', topbar: '52px', sysbar: '30px' },
      borderRadius: { panel: '3px', pill: '2px' },
      boxShadow: {
        panel: '0 1px 0 rgba(255,255,255,0.025) inset',
        raised: '0 1px 0 rgba(255,255,255,0.03) inset, 0 10px 30px -18px rgba(0,0,0,0.95)',
        glow: '0 0 0 1px rgba(61,220,151,0.3), 0 0 18px -6px rgba(61,220,151,0.35)',
      },
      keyframes: {
        pulseDot: { '0%,100%': { opacity: '1' }, '50%': { opacity: '0.3' } },
        sweep: {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(320%)' },
        },
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'pulse-dot': 'pulseDot 2.4s ease-in-out infinite',
        sweep: 'sweep 1.7s ease-in-out infinite',
        'fade-up': 'fadeUp 180ms ease-out',
      },
    },
  },
  plugins: [],
};

export default config;
