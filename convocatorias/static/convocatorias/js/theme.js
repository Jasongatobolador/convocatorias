(function () {
    const body = document.body;
    const toggle = document.getElementById('themeToggle');
    if (!toggle) return;

    const setTheme = (mode) => {
        if (mode === 'dark') {
            body.classList.add('dark');
            toggle.setAttribute('aria-pressed', 'true');
            toggle.querySelector('span').textContent = 'Modo claro';
        } else {
            body.classList.remove('dark');
            toggle.setAttribute('aria-pressed', 'false');
            toggle.querySelector('span').textContent = 'Modo oscuro';
        }
    };

    const saved = localStorage.getItem('theme');
    setTheme(saved === 'dark' ? 'dark' : 'light');

    toggle.addEventListener('click', () => {
        const next = body.classList.contains('dark') ? 'light' : 'dark';
        body.classList.add('theme-fade');
        localStorage.setItem('theme', next);
        setTheme(next);
        setTimeout(() => body.classList.remove('theme-fade'), 220);
    });
})();
