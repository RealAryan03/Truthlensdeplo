// ============ PAGE LOAD & TRANSITIONS ============
document.addEventListener('DOMContentLoaded', () => {
    initApiBaseRouting();
    initPageTransitions();
    initFormValidation();
    initScrollAnimations();
    initButtonInteractions();
    initResultCardAnimations();
    initInputAnimations();
    initNavbarScrollState();
    initCardTilt();
    initOrbParallax();
    initArticleCounter();
    initTooltips();
});

function initApiBaseRouting() {
    const apiBase = (window.__API_BASE_URL || '').trim().replace(/\/$/, '');
    if (!apiBase) return;

    const routedActions = new Set(['/contact', '/forgot-password', '/reset-password', '/predict']);
    document.querySelectorAll('form[action^="/"]').forEach((form) => {
        const action = form.getAttribute('action') || '';
        if (!routedActions.has(action)) return;
        form.setAttribute('action', `${apiBase}${action}`);
    });
}

// Smooth page load animation
function initPageTransitions() {
    document.body.style.opacity = '0';
    document.body.style.transition = 'opacity 0.6s ease-in-out';

    window.addEventListener('pageshow', () => {
        document.body.style.opacity = '1';
    });
    
    setTimeout(() => {
        document.body.style.opacity = '1';
    }, 50);

    // Monitor link clicks for smooth transitions
    document.querySelectorAll('a[href^="/"]').forEach(link => {
        link.addEventListener('click', (e) => {
            if (link.href.includes('/logout')) {
                return;
            }

            const url = new URL(link.href, window.location.origin);
            const isSamePath = url.pathname === window.location.pathname;
            const hasHash = Boolean(url.hash);

            // For same-page anchors (e.g. /about#privacy -> /about#terms), smooth-scroll instead of reloading page.
            if (isSamePath && hasHash) {
                e.preventDefault();
                const target = document.querySelector(url.hash);
                if (target) {
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    history.replaceState(null, '', url.hash);
                }
                return;
            }

            e.preventDefault();
            document.body.style.opacity = '0';
            setTimeout(() => {
                window.location.href = link.href;
            }, 300);
        });
    });
}

// ============ FORM VALIDATION & FEEDBACK ============
function initFormValidation() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        const inputs = form.querySelectorAll('input, textarea');
        
        inputs.forEach(input => {
            // Real-time validation
            input.addEventListener('blur', () => {
                validateField(input);
            });

            input.addEventListener('input', () => {
                if (input.classList.contains('error')) {
                    validateField(input);
                }
            });
        });

        // Form submit with loading state
        form.addEventListener('submit', (e) => {
            let isValid = true;
            inputs.forEach(input => {
                if (!validateField(input)) {
                    isValid = false;
                }
            });

            if (isValid) {
                const btn = form.querySelector('button[type="submit"]');
                if (btn) {
                    btn.classList.add('loading');
                    btn.disabled = true;
                    btn.innerHTML = '⏳ Processing...';
                }
            } else {
                e.preventDefault();
            }
        });
    });
}

function validateField(field) {
    const value = field.value.trim();
    const type = field.type;
    const isValid = true;

    // Remove previous error state
    field.classList.remove('error');
    field.classList.remove('success');

    if (!value) {
        if (field.hasAttribute('required')) {
            field.classList.add('error');
            return false;
        }
    } else {
        if (type === 'email') {
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailRegex.test(value)) {
                field.classList.add('error');
                return false;
            }
        }
        if (type === 'password' && field.name === 'password') {
            if (value.length < 6) {
                field.classList.add('error');
                return false;
            }
        }
        field.classList.add('success');
    }

    return true;
}

// ============ INPUT FIELD ANIMATIONS ============
function initInputAnimations() {
    const inputs = document.querySelectorAll('input, textarea');
    
    inputs.forEach(input => {
        // Focus animation
        input.addEventListener('focus', () => {
            input.parentElement.classList.add('focused');
        });

        input.addEventListener('blur', () => {
            if (!input.value) {
                input.parentElement.classList.remove('focused');
            }
        });

        // Initial state if value exists
        if (input.value) {
            input.parentElement.classList.add('focused');
        }
    });
}

// ============ SCROLL ANIMATIONS ============
function initScrollAnimations() {
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate-in');
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    // Observe cards, sections, and result elements
    document.querySelectorAll('.section-card, .card, .result-cards, .feature-item').forEach(el => {
        observer.observe(el);
    });
}

// ============ BUTTON INTERACTIONS ============
function initButtonInteractions() {
    const buttons = document.querySelectorAll('button, .analyze-btn');
    
    buttons.forEach(btn => {
        // Ripple effect on click
        btn.addEventListener('click', (e) => {
            if (btn.classList.contains('loading')) return;
            
            const ripple = document.createElement('span');
            ripple.classList.add('ripple');
            
            const rect = btn.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            const x = e.clientX - rect.left - size / 2;
            const y = e.clientY - rect.top - size / 2;
            
            ripple.style.width = ripple.style.height = size + 'px';
            ripple.style.left = x + 'px';
            ripple.style.top = y + 'px';
            
            btn.appendChild(ripple);
            
            setTimeout(() => ripple.remove(), 600);
        });

        // Hover scale
        btn.addEventListener('mouseenter', () => {
            if (!btn.disabled) {
                btn.style.transform = 'scale(1.02)';
            }
        });

        btn.addEventListener('mouseleave', () => {
            btn.style.transform = 'scale(1)';
        });
    });
}

// ============ RESULT CARD ANIMATIONS ============
function initResultCardAnimations() {
    const resultCards = document.querySelectorAll('.result-cards .card');
    
    resultCards.forEach((card, index) => {
        // Stagger animation on appearance
        card.style.animationDelay = `${index * 0.1}s`;
        card.classList.add('card-animate');
    });

    // Progress bar animation
    const progressBars = document.querySelectorAll('.progress');
    progressBars.forEach(bar => {
        const rawScore = Number.parseFloat(bar.getAttribute('data-score') || '0');
        const boundedScore = Math.max(0, Math.min(rawScore, 100));
        const targetWidth = `${boundedScore}%`;
        bar.style.width = '0%';
        
        setTimeout(() => {
            bar.style.transition = 'width 1.2s cubic-bezier(0.34, 1.56, 0.64, 1)';
            bar.style.width = targetWidth;
        }, 100);
    });
}

// ============ DYNAMIC TOOLTIPS ============
function initTooltips() {
    document.querySelectorAll('[data-tooltip]').forEach(el => {
        el.addEventListener('mouseenter', () => {
            const tooltip = document.createElement('div');
            tooltip.className = 'tooltip';
            tooltip.textContent = el.getAttribute('data-tooltip');
            document.body.appendChild(tooltip);
            
            const rect = el.getBoundingClientRect();
            tooltip.style.left = (rect.left + rect.width / 2 - tooltip.offsetWidth / 2) + 'px';
            tooltip.style.top = (rect.top - tooltip.offsetHeight - 8) + 'px';
            
            tooltip.classList.add('show');
            
            el.addEventListener('mouseleave', () => {
                tooltip.remove();
            }, { once: true });
        });
    });
}

// ============ NAVBAR ACTIVE STATE ============
function initNavbarActive() {
    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-links a').forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        }
    });
}

function initNavbarScrollState() {
    const navbar = document.querySelector('.navbar');
    if (!navbar) return;

    const onScroll = () => {
        navbar.classList.toggle('scrolled', window.scrollY > 8);
    };

    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
}

function initCardTilt() {
    const cards = document.querySelectorAll('.card, .section-card, .hero-card');

    cards.forEach((card) => {
        card.addEventListener('mousemove', (e) => {
            if (window.innerWidth < 900) return;

            const rect = card.getBoundingClientRect();
            const x = (e.clientX - rect.left) / rect.width;
            const y = (e.clientY - rect.top) / rect.height;
            const rotateY = (x - 0.5) * 4;
            const rotateX = (0.5 - y) * 3;

            card.style.transform = `perspective(900px) rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
        });

        card.addEventListener('mouseleave', () => {
            card.style.transform = '';
        });
    });
}

function initOrbParallax() {
    const orbs = document.querySelectorAll('.bg-orb');
    if (!orbs.length) return;

    window.addEventListener('pointermove', (e) => {
        const x = (e.clientX / window.innerWidth - 0.5) * 14;
        const y = (e.clientY / window.innerHeight - 0.5) * 14;

        orbs.forEach((orb, index) => {
            const factor = (index + 1) * 0.35;
            orb.style.transform = `translate(${x * factor}px, ${y * factor}px)`;
        });
    });
}

function initArticleCounter() {
    const articleField = document.querySelector('textarea[name="article"]');
    const counter = document.querySelector('#article-char-count');
    if (!articleField || !counter) return;

    const draftKey = 'truthlens.articleDraft';
    const savedDraft = sessionStorage.getItem(draftKey);

    // Restore any unsent draft when the field is empty on load.
    if (!articleField.value && savedDraft) {
        articleField.value = savedDraft;
    }

    const syncCount = () => {
        const total = articleField.value.trim().length;
        counter.textContent = `${total} chars`;
    };

    syncCount();
    articleField.addEventListener('input', () => {
        sessionStorage.setItem(draftKey, articleField.value);
        syncCount();
    });

    // Keep session draft aligned with server-rendered value after analysis.
    sessionStorage.setItem(draftKey, articleField.value);
}

// ============ SMOOTH SCROLL FOR ANCHORS ============
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// ============ KEYBOARD SHORTCUTS ============
document.addEventListener('keydown', (e) => {
    // ESC to close modals or alerts
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal.opened').forEach(modal => {
            modal.classList.remove('opened');
        });
    }

    // CTRL+K or CMD+K for focus on analyze button (quick action)
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        const analyzeBtn = document.querySelector('.analyze-btn');
        if (analyzeBtn) {
            analyzeBtn.focus();
        }
    }
});

// ============ LAZY LOADING FOR IMAGES ============
if ('IntersectionObserver' in window) {
    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.classList.add('loaded');
                observer.unobserve(img);
            }
        });
    });

    document.querySelectorAll('img[data-src]').forEach(img => {
        imageObserver.observe(img);
    });
}

// ============ DARK MODE TOGGLE (Optional) ============
function initDarkMode() {
    const isDarkMode = localStorage.getItem('darkMode') === 'true';
    if (isDarkMode) {
        document.body.classList.add('dark-mode');
    }
}

// Initialize navbar active state
initNavbarActive();

// Make tooltip system globally available
window.showTooltip = (el, text) => {
    const tooltip = document.createElement('div');
    tooltip.className = 'tooltip show';
    tooltip.textContent = text;
    el.appendChild(tooltip);
};

console.log('✨ TruthLens Interactive Features Loaded');
