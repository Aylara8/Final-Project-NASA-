document.addEventListener('DOMContentLoaded', () => {
    // 0. Splash Screen Logic
    const splash = document.getElementById('splash-screen');
    if (splash) {
        if (sessionStorage.getItem('splashPlayed')) {
            splash.style.display = 'none';
        } else {
            setTimeout(() => {
                splash.classList.add('fade-out');
                sessionStorage.setItem('splashPlayed', 'true');
            }, 3000);
        }
    }

    // 1. Theme Logic
    const themeBtn = document.getElementById('theme-toggle');
    const html = document.documentElement;
    const themeIcon = themeBtn.querySelector('i');

    const savedTheme = localStorage.getItem('theme') || 'light';
    html.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);

    themeBtn.addEventListener('click', () => {
        const currentTheme = html.getAttribute('data-theme');
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        html.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        updateThemeIcon(newTheme);
    });

    function updateThemeIcon(theme) {
        if (theme === 'dark') {
            themeIcon.classList.replace('fa-moon', 'fa-sun');
        } else {
            themeIcon.classList.replace('fa-sun', 'fa-moon');
        }
    }

    // 2. User Menu Dropdown
    const userMenuBtn = document.querySelector('.user-menu-btn');
    const userDropdown = document.querySelector('.user-dropdown');

    if (userMenuBtn && userDropdown) {
        userMenuBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            userDropdown.classList.toggle('show');
        });

        document.addEventListener('click', () => {
            userDropdown.classList.remove('show');
        });
    }

    // 3. Category Selection & Filtering
    const categoryItems = document.querySelectorAll('.category-item');
    const cards = document.querySelectorAll('.hs-card');

    categoryItems.forEach(item => {
        item.addEventListener('click', () => {
            // Update Active State
            categoryItems.forEach(i => i.classList.remove('active'));
            item.classList.add('active');
            
            const selectedCategory = item.getAttribute('data-category');
            
            // Filter Cards
            cards.forEach(card => {
                const cardCategory = card.getAttribute('data-category');
                
                if (selectedCategory === 'all' || cardCategory === selectedCategory) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
            
            console.log(`Filtered by: ${selectedCategory}`);
        });
    });

    // 4. Search Filter
    const searchBar = document.querySelector('.search-bar');
    if (searchBar) {
        searchBar.addEventListener('click', () => {
            console.log('Search clicked');
            // Show search overlay or focus input
        });
    }
});