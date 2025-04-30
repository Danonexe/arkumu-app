/* Project specific Javascript goes here. */

// Theme switcher functionality
document.addEventListener('DOMContentLoaded', function() {
  const themeButtons = document.querySelectorAll('[data-theme]');
  
  themeButtons.forEach(button => {
    button.addEventListener('click', function() {
      const theme = this.getAttribute('data-theme');
      // Add theme class to BODY instead of HTML element
      document.body.classList.remove('theme-dark', 'theme-light', 'theme-blue');
      document.body.classList.add(`theme-${theme}`);
      
      // Update button states
      themeButtons.forEach(btn => {
        btn.classList.remove('ring-2', 'ring-white');
      });
      this.classList.add('ring-2', 'ring-white');
      
      // Store preference (optional)
      localStorage.setItem('arkumu-theme', theme);
      
      console.log(`Theme switched to: ${theme}`);
    });
  });
  
  // Apply saved theme on page load
  const savedTheme = localStorage.getItem('arkumu-theme') || 'light'; // Default to light
  if (savedTheme) {
    // Add theme class to BODY instead of HTML element
    document.body.classList.remove('theme-dark', 'theme-light', 'theme-blue');
    document.body.classList.add(`theme-${savedTheme}`);
    
    // Update button state for saved theme
    const activeButton = document.querySelector(`[data-theme="${savedTheme}"]`);
    if (activeButton) {
      activeButton.classList.add('ring-2', 'ring-white');
    }
    
    console.log(`Initial theme: ${savedTheme}`);
  }
});
