(() => {
    const nav = document.querySelector('.site-nav');
    const toggle = document.querySelector('.mobile-nav-toggle');
    const menu = document.getElementById('siteNavMenu');

    if (!nav || !toggle || !menu) return;

    const mobileQuery = window.matchMedia('(max-width: 900px)');

    function setOpen(open, { focusToggle = false } = {}) {
        const shouldOpen = Boolean(open && mobileQuery.matches);
        nav.classList.toggle('mobile-open', shouldOpen);
        toggle.setAttribute('aria-expanded', String(shouldOpen));
        toggle.setAttribute(
            'aria-label',
            shouldOpen ? 'Close navigation menu' : 'Open navigation menu'
        );
        document.body.classList.toggle('mobile-nav-open', shouldOpen);

        if (focusToggle) toggle.focus();
    }

    toggle.addEventListener('click', () => {
        const isOpen = toggle.getAttribute('aria-expanded') === 'true';
        setOpen(!isOpen);
    });

    menu.addEventListener('click', event => {
        if (event.target.closest('a')) setOpen(false);
    });

    document.addEventListener('click', event => {
        if (!nav.contains(event.target)) setOpen(false);
    });

    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && nav.classList.contains('mobile-open')) {
            setOpen(false, { focusToggle: true });
        }
    });

    mobileQuery.addEventListener?.('change', event => {
        if (!event.matches) setOpen(false);
    });
})();
