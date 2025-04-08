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
        // Light Mode
        light: {
          bg: '#FFFFFF',
          text: {
            primary: '#000000',
            secondary: '#4A4A4A',
          },
          button: {
            bg: {
              primary: '#1A1A1A',
              secondary: '#6B6B6B',
              outline: 'transparent',
            },
            text: {
              primary: '#FFFFFF',
              secondary: '#FFFFFF',
              outline: '#000000',
            },
            border: {
              primary: '#1A1A1A',
              secondary: '#6B6B6B',
              outline: '#000000',
            }
          }
        },
        
        // Dark Mode
        dark: {
          bg: '#1A1A1A',
          text: {
            primary: '#FFFFFF',
            secondary: '#E0E0E0',
          },
          button: {
            bg: {
              primary: '#FFFFFF',
              secondary: '#6B6B6B',
              outline: 'transparent',
            },
            text: {
              primary: '#000000',
              secondary: '#FFFFFF',
              outline: '#FFFFFF',
            },
            border: {
              primary: '#FFFFFF',
              secondary: '#6B6B6B',
              outline: '#FFFFFF',
            }
          }
        },
        
        // Blue Mode
        blue: {
          bg: '#FFFFFF',
          text: {
            primary: '#1967D2',
            secondary: '#4285F4',
          },
          button: {
            bg: {
              primary: '#1967D2',
              secondary: '#4285F4',
              outline: 'transparent',
            },
            text: {
              primary: '#FFFFFF',
              secondary: '#FFFFFF',
              outline: '#1967D2',
            },
            border: {
              primary: '#1967D2',
              secondary: '#4285F4',
              outline: '#1967D2',
            }
          }
        }
      }
    }
  },
  plugins: [],
}