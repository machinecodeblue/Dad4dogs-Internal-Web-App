 (function () {
        var toggle = document.getElementById('nav-menu-toggle');
        var drawer = document.getElementById('nav-drawer');
        var backdrop = document.getElementById('nav-drawer-backdrop');
        var closeBtn = document.getElementById('nav-drawer-close');
        if (!toggle || !drawer || !backdrop) return;

        function setOpen(open) {
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
            drawer.classList.toggle('hidden', !open);
            backdrop.classList.toggle('hidden', !open);
            if (open) {
                drawer.removeAttribute('hidden');
                backdrop.removeAttribute('hidden');
            } else {
                drawer.setAttribute('hidden', '');
                backdrop.setAttribute('hidden', '');
            }
        }

        toggle.addEventListener('click', function () {
            setOpen(toggle.getAttribute('aria-expanded') !== 'true');
        });
        closeBtn && closeBtn.addEventListener('click', function () { setOpen(false); });
        backdrop.addEventListener('click', function () { setOpen(false); });
        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') setOpen(false);
        });
    })();
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', function () {
            navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function () {});
        });
    }