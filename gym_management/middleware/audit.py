import logging

from accounts.utils import get_user_role


logger = logging.getLogger('security.audit')


class AuditMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.user.is_authenticated:
            logger.info(
                'USER_ACCESS | user=%s | role=%s | method=%s | path=%s | status=%s | ip=%s',
                request.user.email,
                get_user_role(request.user),
                request.method,
                request.path,
                response.status_code,
                self.get_client_ip(request),
            )

        return response

    @staticmethod
    def get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')
