/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  // 主题切换：<html data-theme="dark"> 下启用 dark: 变体（P0 地基）
  darkMode: ['selector', '[data-theme="dark"]'],
  theme: {
    extend: {
      // 矮视口变体：MacBook Air 等笔记本屏（可用高度≤840px）下启用紧凑档
      screens: {
        short: { raw: '(max-height: 840px)' },
      },
      colors: {
        // 「小O」设计稿配色：科技蓝 #256BFF + 纯净白，浅蓝 #7DD3FC(=sky-300)，屏幕深蓝 #0D1B2A
        brand: {
          50: '#EAF1FF',
          100: '#D6E4FF',
          200: '#B3CCFF',
          300: '#85AEFF',
          400: '#4D8BFF',
          500: '#256BFF', // Primary 科技蓝
          600: '#1A54E8', // hover / 深色
          700: '#1A45C0',
          800: '#17389A',
          900: '#0D1B2A', // 屏幕深蓝
        },
        // 语义色标（CSS 变量驱动，随主题翻转）——存量 text-ink / bg-surface 自动生效
        ink: {
          DEFAULT: 'var(--ink)',
          soft: 'var(--ink-soft)',
          muted: 'var(--ink-muted)',
        },
        surface: {
          DEFAULT: 'var(--surface)',
          variant: 'var(--surface-variant)',
          sunken: 'var(--surface-sunken)',
        },
        price: '#E53935',
        score: {
          high: '#2E7D32',
          mid: '#3E68D9',
          low: '#C62828',
        },
        risk: {
          bg: '#FFF3E0',
          text: '#BF360C',
        },
      },
      fontFamily: {
        sans: [
          '"PingFang SC"',
          '"Helvetica Neue"',
          'Helvetica',
          '"Microsoft YaHei"',
          'Arial',
          'system-ui',
          'sans-serif',
        ],
      },
      borderRadius: {
        xl2: '1.25rem',
      },
      boxShadow: {
        card: '0 1px 2px rgba(16, 24, 40, 0.04), 0 1px 3px rgba(16, 24, 40, 0.06)',
        float: '0 8px 30px rgba(36, 87, 214, 0.12)',
        glow: '0 0 0 3px rgba(74, 125, 255, 0.15)',
        glass: '0 8px 32px rgba(37, 107, 255, 0.10), inset 0 1px 0 rgba(255, 255, 255, 0.6)',
        lift: '0 12px 32px rgba(13, 27, 42, 0.10)',
        'glow-lg': '0 0 24px rgba(37, 107, 255, 0.25)',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-up': {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'scale-in': {
          '0%': { opacity: '0', transform: 'scale(0.96)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.2' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
        blob: {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)' },
          '33%': { transform: 'translate(24px, -32px) scale(1.08)' },
          '66%': { transform: 'translate(-18px, 20px) scale(0.94)' },
        },
        'pulse-glow': {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(37, 107, 255, 0.35)' },
          '50%': { boxShadow: '0 0 0 8px rgba(37, 107, 255, 0)' },
        },
        'bounce-soft': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-3px)' },
        },
        wave: {
          '0%, 100%': { transform: 'scaleY(0.4)' },
          '50%': { transform: 'scaleY(1)' },
        },
        breathe: {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.75', transform: 'scale(1.12)' },
        },
        // 首屏聚光呼吸（P1）
        'spot-breathe': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.55' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.3s ease-out',
        'slide-up': 'slide-up 0.35s cubic-bezier(0.22, 1, 0.36, 1)',
        'scale-in': 'scale-in 0.2s ease-out',
        blink: 'blink 1s step-start infinite',
        shimmer: 'shimmer 1.6s infinite',
        blob: 'blob 14s ease-in-out infinite',
        'blob-slow': 'blob 20s ease-in-out infinite reverse',
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        'bounce-soft': 'bounce-soft 0.9s ease-in-out infinite',
        breathe: 'breathe 1.8s ease-in-out infinite',
        'spot-breathe': 'spot-breathe 4.5s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
