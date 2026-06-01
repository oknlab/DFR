import daisyui from 'daisyui'

export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {},
  },
  plugins: [daisyui],
  daisyui: {
    themes: [
      {
        oknlab: {
          'base-100': '#020617',
          'base-200': '#0f172a',
          'base-300': '#1e293b',
          'base-content': '#f8fafc',
          primary: '#34d399',
          'primary-content': '#020617',
          secondary: '#67e8f9',
          accent: '#fbbf24',
          neutral: '#0f172a',
          info: '#60a5fa',
          success: '#34d399',
          warning: '#facc15',
          error: '#f87171',
        },
      },
    ],
  },
}
