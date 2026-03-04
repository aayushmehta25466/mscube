"""
Security headers middleware for enhanced protection.
Maps to NIST/OWASP security recommendations.
"""
from django.conf import settings


class SecurityHeadersMiddleware:
    """
    Add security headers to all HTTP responses.
    
    Headers added:
    - X-Content-Type-Options: nosniff (prevent MIME sniffing attacks)
    - X-Frame-Options: DENY (prevent clickjacking) 
    - X-XSS-Protection: 1; mode=block (XSS filtering)
    - Referrer-Policy: strict-origin-when-cross-origin (limit referrer leakage)
    - Content-Security-Policy: restrictive CSP (prevent code injection)
    - Permissions-Policy: restrictive feature policy (limit browser APIs)
    
    Production-only headers when DEBUG=False:
    - Strict-Transport-Security: enforce HTTPS
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Base security headers (always applied)
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY' 
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Content Security Policy - restrictive for gym management app
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline'",  # Tailwind may need inline styles
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: https:",  # Allow images from data URLs and HTTPS
            "connect-src 'self'",
            "frame-ancestors 'none'",  # Equivalent to X-Frame-Options: DENY
            "base-uri 'self'",
            "form-action 'self'",
        ]
        
        # Add upgrade-insecure-requests in production
        if not settings.DEBUG:
            csp_directives.append("upgrade-insecure-requests")
        
        response['Content-Security-Policy'] = '; '.join(csp_directives)
        
        # Permissions Policy - limit browser APIs for security
        permissions_directives = [
            'camera=()',
            'microphone=()',
            'geolocation=()',
            'interest-cohort=()',  # Disable FLoC tracking
            'payment=(self)',  # Allow payment APIs on same origin only
            'accelerometer=()',
            'ambient-light-sensor=()',
            'autoplay=()',
            'battery=()',
            'display-capture=()',
            'gyroscope=()',
            'magnetometer=()',
            'usb=()',
        ]
        response['Permissions-Policy'] = ', '.join(permissions_directives)

        # Production-only headers (HTTPS enforcement)
        if not settings.DEBUG:
            # Strict Transport Security - 1 year max-age with subdomains
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
            
            # Additional production headers
            response['X-Permitted-Cross-Domain-Policies'] = 'none'
            response['Cross-Origin-Embedder-Policy'] = 'require-corp'
            response['Cross-Origin-Opener-Policy'] = 'same-origin'
            response['Cross-Origin-Resource-Policy'] = 'same-origin'

        return response
