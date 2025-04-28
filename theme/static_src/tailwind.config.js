module.exports = {
  content: [
    // Templates in your Django project
    '../../**/templates/**/*.html',
    '../../**/templates/**/*.py',  
    // JavaScript files that might contain Tailwind classes
    './js/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        arkumu: {
          dark: '#2D2D2D',
          'dark-hover': '#3A3A3A',
          'dark-passive': '#656565',
          light: '#FFFFFF',
          'light-hover': '#E6E6E6',
          // Nuevos colores para los botones
          'blau': '#4285F4',       // Color azul para el botón "Blau"
          'hell': '#F8F7F4',       // Color claro/beige para el botón "Hell"
          'dunkel': '#1D1D1D',     // Color oscuro/negro para el botón "Dunkel"
        },
      },
      fontFamily: {
        sans: ['Roboto Mono', 'monospace'],
        mono: ['Roboto Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}