from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils import timezone


class WorkerSessionTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            return self.get_response(request)

        is_worker_session = (
            request.user.is_superuser
            or (hasattr(request.user, "trabajador_perfil") and request.user.trabajador_perfil.activo)
        )
        is_final_user_session = not is_worker_session
        now_ts = timezone.now().timestamp()

        if is_worker_session and request.path.startswith("/trabajador/"):
            timeout_seconds = getattr(settings, "WORKER_SESSION_TIMEOUT_SECONDS", 1800)
            last_activity = request.session.get("worker_last_activity")
            if last_activity and now_ts - last_activity > timeout_seconds:
                logout(request)
                messages.error(request, "Sesion cerrada por inactividad.")
                return redirect("login_trabajador")
            request.session["worker_last_activity"] = now_ts

        if is_final_user_session and request.path.startswith(("/convocatorias/", "/detalle/", "/usuario/")):
            timeout_seconds = getattr(settings, "USER_SESSION_TIMEOUT_SECONDS", 1800)
            last_activity = request.session.get("user_last_activity")
            if last_activity and now_ts - last_activity > timeout_seconds:
                logout(request)
                messages.error(request, "Sesion cerrada por inactividad.")
                return redirect("login")
            request.session["user_last_activity"] = now_ts

        return self.get_response(request)


class SecurityHeadersMiddleware:
    CSP = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "frame-ancestors 'self'; "
        "object-src 'none'; "
        "form-action 'self'; "
        "img-src 'self' data:; "
        "script-src 'self'; "
        "style-src 'self'; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-src 'self'"
    )

    PERMISSIONS_POLICY = "camera=(), geolocation=(), microphone=(), payment=(), usb=()"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Content-Security-Policy"] = self.CSP
        response["Permissions-Policy"] = self.PERMISSIONS_POLICY
        response["X-Frame-Options"] = "SAMEORIGIN"
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response["X-Permitted-Cross-Domain-Policies"] = "none"
        
        static_prefix = getattr(settings, "STATIC_URL", "/static/")
        media_prefix = getattr(settings, "MEDIA_URL", "/media/")
        path = getattr(request, "path", "")
        if not path.startswith((static_prefix, media_prefix)):
            content_type = response.get("Content-Type", "")
            if content_type.startswith("text/html") or path.startswith((
                "/usuario/documento/",
                "/trabajador/solicitud/",
            )):
                response["Cache-Control"] = "no-store, max-age=0, must-revalidate, private"
                response["Pragma"] = "no-cache"
                response["Expires"] = "0"

        return response
