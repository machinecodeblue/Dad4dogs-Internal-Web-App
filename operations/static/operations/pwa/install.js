(function () {
    const DISMISS_KEY = 'dad4dogs-pwa-install-dismissed';
    const INSTALLED_KEY = 'dad4dogs-pwa-installed';
    const banner = document.getElementById('custom-install-banner');
    const iosOverlay = document.getElementById('ios-install-overlay');
    const androidOverlay = document.getElementById('android-install-overlay');
    const installBtn = document.getElementById('custom-install-btn');
    const guideInstallBtn = document.getElementById('guide-install-btn');
    const dismissBtn = document.getElementById('custom-install-dismiss');
    const iosOverlayDismiss = document.getElementById('ios-install-overlay-dismiss');
    const androidOverlayDismiss = document.getElementById('android-install-overlay-dismiss');
    const subtitle = document.getElementById('install-banner-subtitle');

    if (!banner) {
        return;
    }

    let deferredPrompt = null;

    function isInstalled() {
        if (window.matchMedia('(display-mode: standalone)').matches
            || window.navigator.standalone === true) {
            return true;
        }
        try {
            return localStorage.getItem(INSTALLED_KEY) === '1';
        } catch (err) {
            return false;
        }
    }

    function isDismissed() {
        try {
            return localStorage.getItem(DISMISS_KEY) === '1';
        } catch (err) {
            return false;
        }
    }

    function hideOverlays() {
        if (iosOverlay) {
            iosOverlay.classList.add('hidden');
        }
        if (androidOverlay) {
            androidOverlay.classList.add('hidden');
        }
    }

    function hideBanner() {
        banner.classList.add('hidden');
        hideOverlays();
    }

    function dismissBanner() {
        try {
            localStorage.setItem(DISMISS_KEY, '1');
        } catch (err) {
            /* ignore */
        }
        hideBanner();
    }

    function markInstalledForever() {
        try {
            localStorage.setItem(INSTALLED_KEY, '1');
            localStorage.setItem(DISMISS_KEY, '1');
        } catch (err) {
            /* ignore */
        }
        hideBanner();
    }

    function setVisibleCta(mode) {
        if (installBtn) {
            const showNativeInstall = mode === 'android' || (mode === 'desktop' && deferredPrompt);
            installBtn.classList.toggle('hidden', !showNativeInstall);
        }
        if (guideInstallBtn) {
            guideInstallBtn.classList.toggle('hidden', mode !== 'ios');
        }
    }

    function showBanner(mode) {
        if (isInstalled() || isDismissed()) {
            return;
        }
        banner.dataset.mode = mode;
        setVisibleCta(mode);
        if (subtitle) {
            if (mode === 'ios') {
                subtitle.textContent = 'Tap INSTALL, then Share → Add to Home Screen in Safari.';
            } else if (mode === 'desktop') {
                subtitle.textContent = 'Tap INSTALL or use your browser menu to add Dad4dogs.';
            } else if (mode === 'android') {
                subtitle.textContent = deferredPrompt
                    ? 'Tap INSTALL to add Dad4dogs to your home screen.'
                    : 'Tap INSTALL for steps, or use Chrome menu → Install app.';
            } else {
                subtitle.textContent = 'Get instant access to check-in and your daily agenda from your home screen.';
            }
        }
        banner.classList.remove('hidden');
    }

    function isIOS() {
        return /iPad|iPhone|iPod/.test(navigator.userAgent)
            || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    }

    function isAndroid() {
        return /Android/i.test(navigator.userAgent);
    }

    if (dismissBtn) {
        dismissBtn.addEventListener('click', dismissBanner);
    }

    if (iosOverlayDismiss) {
        iosOverlayDismiss.addEventListener('click', hideOverlays);
    }

    if (androidOverlayDismiss) {
        androidOverlayDismiss.addEventListener('click', hideOverlays);
    }

    if (guideInstallBtn) {
        guideInstallBtn.addEventListener('click', function () {
            if (iosOverlay) {
                iosOverlay.classList.remove('hidden');
            }
        });
    }

    if (installBtn) {
        installBtn.addEventListener('click', async function () {
            if (deferredPrompt) {
                deferredPrompt.prompt();
                const choice = await deferredPrompt.userChoice;
                if (choice.outcome === 'accepted') {
                    markInstalledForever();
                }
                deferredPrompt = null;
                return;
            }
            if (isAndroid() && androidOverlay) {
                androidOverlay.classList.remove('hidden');
            }
        });
    }

    window.addEventListener('beforeinstallprompt', function (event) {
        event.preventDefault();
        deferredPrompt = event;
        const mode = isAndroid() ? 'android' : 'desktop';
        showBanner(mode);
    });

    window.addEventListener('appinstalled', markInstalledForever);

    if (isInstalled() || isDismissed()) {
        return;
    }

    if (isIOS()) {
        showBanner('ios');
        return;
    }

    if (isAndroid()) {
        window.setTimeout(function () {
            if (!isDismissed() && !isInstalled()) {
                showBanner('android');
            }
        }, 2000);
        return;
    }

    window.setTimeout(function () {
        if (!deferredPrompt && !isDismissed() && !isInstalled()) {
            showBanner('desktop');
        }
    }, 2000);
})();