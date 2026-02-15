// Mobile Navigation Toggle
const hamburger = document.getElementById('hamburger');
const navMenu = document.getElementById('navMenu');

if (hamburger && navMenu) {
    hamburger.addEventListener('click', () => {
        hamburger.classList.toggle('active');
        navMenu.classList.toggle('active');
    });

    // Close menu when clicking on a link
    const navLinks = navMenu.querySelectorAll('a');
    navLinks.forEach(link => {
        link.addEventListener('click', () => {
            hamburger.classList.remove('active');
            navMenu.classList.remove('active');
        });
    });

    // Close menu when clicking outside
    document.addEventListener('click', (e) => {
        if (!hamburger.contains(e.target) && !navMenu.contains(e.target)) {
            hamburger.classList.remove('active');
            navMenu.classList.remove('active');
        }
    });
}

// Navbar scroll effect
let lastScroll = 0;
const navbar = document.querySelector('.navbar');

window.addEventListener('scroll', () => {
    const currentScroll = window.pageYOffset;
    
    if (currentScroll <= 0) {
        navbar.style.boxShadow = 'none';
    } else {
        navbar.style.boxShadow = '0 2px 10px rgba(0, 0, 0, 0.3)';
    }
    
    lastScroll = currentScroll;
});

// Smooth scroll for anchor links
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

// Animate elements on scroll
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, observerOptions);

// Observe all cards and sections
const animateElements = document.querySelectorAll(
    '.stat-card, .program-card, .trainer-card, .contact-card'
);

animateElements.forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(30px)';
    el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
    observer.observe(el);
});

// Counter animation for stats
const animateCounter = (element, target, duration = 2000) => {
    const start = 0;
    const increment = target / (duration / 16); // 60fps
    let current = start;
    
    const timer = setInterval(() => {
        current += increment;
        if (current >= target) {
            element.textContent = formatNumber(target);
            clearInterval(timer);
        } else {
            element.textContent = formatNumber(Math.floor(current));
        }
    }, 16);
};

const formatNumber = (num) => {
    if (num >= 1000) {
        return (num / 1000).toFixed(0) + 'K+';
    }
    return num + '+';
};

// Trigger counter animation when stats are visible
const statsObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const statNumber = entry.target.querySelector('.stat-number');
            const text = statNumber.textContent;
            const numberMatch = text.match(/(\d+)/);
            
            if (numberMatch) {
                const targetNumber = parseInt(numberMatch[0]);
                animateCounter(statNumber, targetNumber);
                statsObserver.unobserve(entry.target);
            }
        }
    });
}, { threshold: 0.5 });

document.querySelectorAll('.stat-card').forEach(card => {
    statsObserver.observe(card);
});

// CTA Button click handler — navigate to contact page instead of showing registration alert
const ctaBtns = document.querySelectorAll('.cta-btn, .btn-primary');
ctaBtns.forEach(btn => {
    btn.addEventListener('click', (e) => {
        // If element is an anchor, allow default navigation
        if (btn.tagName === 'A' && btn.getAttribute('href')) return;

        // Otherwise, navigate to contact page
        window.location.href = 'contact.html';
    });
});

// Add ripple effect to buttons
const createRipple = (event) => {
    const button = event.currentTarget;
    const ripple = document.createElement('span');
    const diameter = Math.max(button.clientWidth, button.clientHeight);
    const radius = diameter / 2;

    ripple.style.width = ripple.style.height = `${diameter}px`;
    ripple.style.left = `${event.clientX - button.offsetLeft - radius}px`;
    ripple.style.top = `${event.clientY - button.offsetTop - radius}px`;
    ripple.classList.add('ripple');

    const existingRipple = button.querySelector('.ripple');
    if (existingRipple) {
        existingRipple.remove();
    }

    button.appendChild(ripple);
};

document.querySelectorAll('.btn, .cta-btn').forEach(button => {
    button.addEventListener('click', createRipple);
});

// Add CSS for ripple effect
const style = document.createElement('style');
style.textContent = `
    .btn, .cta-btn {
        position: relative;
        overflow: hidden;
    }
    
    .ripple {
        position: absolute;
        border-radius: 50%;
        background: rgba(255, 255, 255, 0.3);
        transform: scale(0);
        animation: ripple-animation 0.6s ease-out;
        pointer-events: none;
    }
    
    @keyframes ripple-animation {
        to {
            transform: scale(4);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// Form validation (for future contact forms)
const validateEmail = (email) => {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
};

const validatePhone = (phone) => {
    const re = /^[\d\s\-\+\(\)]+$/;
    return re.test(phone);
};

// Lazy loading for images (when you add real images)
if ('loading' in HTMLImageElement.prototype) {
    const images = document.querySelectorAll('img[loading="lazy"]');
    images.forEach(img => {
        img.src = img.dataset.src;
    });
} else {
    // Fallback for browsers that don't support lazy loading
    const script = document.createElement('script');
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/lazysizes/5.3.2/lazysizes.min.js';
    document.body.appendChild(script);
}

// Console message for developers
console.log('%c Welcome to MSCUBEGYM! ', 'background: #6b7d9d; color: white; font-size: 20px; padding: 10px;');
console.log('%c Transform your body, elevate your mind. ', 'color: #6b7d9d; font-size: 14px;');

// Performance monitoring
window.addEventListener('load', () => {
    const loadTime = performance.timing.loadEventEnd - performance.timing.navigationStart;
    console.log(`Page loaded in ${loadTime}ms`);
});

// Trainer modal: open trainer details on top of the page without navigating away
function openTrainerModal(data) {
    // Prevent duplicate modal
    if (document.querySelector('.trainer-modal')) return;

    const overlay = document.createElement('div');
    overlay.className = 'trainer-modal';

    overlay.innerHTML = `
        <div class="trainer-modal-content">
            <button class="trainer-modal-close" aria-label="Close">×</button>
            <div class="trainer-modal-body">
                <div class="trainer-modal-image"><img src="${data.img}" alt="${data.name}"></div>
                <div class="trainer-modal-info">
                    <h2>${data.name}</h2>
                    <p class="experience">${data.experience}</p>
                    <p class="trainer-bio">${data.bio}</p>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);

    // Close handlers
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.remove();
    });

    const closeBtn = overlay.querySelector('.trainer-modal-close');
    closeBtn.addEventListener('click', () => overlay.remove());
}

// Attach click handlers to trainer links on the homepage
document.querySelectorAll('.trainer-link').forEach(link => {
    link.addEventListener('click', (e) => {
        // Allow modifier keys to open in new tab
        if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;

        e.preventDefault();

        const data = {
            name: link.getAttribute('data-name') || '',
            specialty: link.getAttribute('data-specialty') || '',
            experience: link.getAttribute('data-experience') || '',
            bio: link.getAttribute('data-bio') || '',
            img: link.getAttribute('data-img') || ''
        };

        openTrainerModal(data);
    });
});