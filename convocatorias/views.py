from datetime import datetime, time, timedelta
import base64
import mimetypes
import random
from pathlib import Path
import uuid

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash, get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    CambiarContrasenaForm,
    FiltroTrabajadorForm,
    PerfilUsuarioForm,
    RegistroForm,
    RevisionRechazoForm,
    SubidaDocumentoForm,
    TrabajadorLoginForm,
)
from .models import (
    Convocatoria,
    ConvocatoriaDocumentoConfiguracion,
    DocumentoCatalogo,
    DocumentoUsuario,
    EventoAuditoria,
    IntentoLoginTrabajador,
    IntentoLoginUsuario,
    Inscripcion,
    NotificacionUsuario,
    PasswordResetAttempt,
    PasswordResetCode,
    PerfilUsuario,
    SolicitudRevision,
    TrabajadorPerfil,
)

DOCUMENTOS_BASE_CODIGOS = [
    DocumentoUsuario.Tipo.IDENTIFICACION,
    DocumentoUsuario.Tipo.CURP,
    DocumentoUsuario.Tipo.COMPROBANTE_DOMICILIO,
]


def _get_client_ip(request):
    if getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _registrar_fallo_login_trabajador(email, ip):
    intento, _ = IntentoLoginTrabajador.objects.get_or_create(
        username=email,
        ip=ip,
        defaults={"intentos_fallidos": 0},
    )
    intento.intentos_fallidos += 1
    max_intentos = max(int(getattr(settings, "WORKER_MAX_LOGIN_FAILED", 5)), 1)
    minutos_bloqueo = max(int(getattr(settings, "WORKER_LOGIN_BLOCK_MINUTES", 15)), 1)
    if intento.intentos_fallidos >= max_intentos:
        intento.bloqueado_hasta = timezone.now() + timedelta(minutes=minutos_bloqueo)
        intento.intentos_fallidos = 0
    intento.save(update_fields=["intentos_fallidos", "bloqueado_hasta", "actualizado_en"])


def _intento_login_trabajador_bloqueado(email, ip):
    intento = IntentoLoginTrabajador.objects.filter(username=email, ip=ip).first()
    if not intento or not intento.bloqueado_hasta:
        return False, 0
    if intento.bloqueado_hasta <= timezone.now():
        intento.bloqueado_hasta = None
        intento.save(update_fields=["bloqueado_hasta", "actualizado_en"])
        return False, 0
    segundos_restantes = int((intento.bloqueado_hasta - timezone.now()).total_seconds())
    minutos = max((segundos_restantes + 59) // 60, 1)
    return True, minutos


def _limpiar_intentos_login_trabajador(email, ip):
    IntentoLoginTrabajador.objects.filter(username=email, ip=ip).delete()


def _user_is_worker(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return hasattr(user, "trabajador_perfil") and user.trabajador_perfil.activo


def _user_is_final(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return False
    return not hasattr(user, "trabajador_perfil")


def _final_user_required(request):
    if _user_is_final(request.user):
        return None
    if request.user.is_authenticated and _user_is_worker(request.user):
        messages.error(request, "Tu cuenta es de trabajador. Accede desde el panel correspondiente.")
        return redirect("dashboard_trabajador")
    if request.user.is_authenticated and request.user.is_superuser:
        messages.error(request, "Acceso disponible solo para usuarios finales.")
        return redirect("/Direcion-del-desarrollo-economico-sostenible/")
    messages.error(request, "Debes iniciar sesion para continuar.")
    return redirect("login")


def _registrar_fallo_login_usuario(email, ip):
    intento, _ = IntentoLoginUsuario.objects.get_or_create(
        username=email,
        ip=ip,
        defaults={"intentos_fallidos": 0},
    )
    intento.intentos_fallidos += 1
    max_intentos = max(int(getattr(settings, "USER_MAX_LOGIN_FAILED", 5)), 1)
    minutos_bloqueo = max(int(getattr(settings, "USER_LOGIN_BLOCK_MINUTES", 15)), 1)
    if intento.intentos_fallidos >= max_intentos:
        intento.bloqueado_hasta = timezone.now() + timedelta(minutes=minutos_bloqueo)
        intento.intentos_fallidos = 0
    intento.save(update_fields=["intentos_fallidos", "bloqueado_hasta", "actualizado_en"])


def _intento_login_usuario_bloqueado(email, ip):
    intento = IntentoLoginUsuario.objects.filter(username=email, ip=ip).first()
    if not intento or not intento.bloqueado_hasta:
        return False, 0
    if intento.bloqueado_hasta <= timezone.now():
        intento.bloqueado_hasta = None
        intento.save(update_fields=["bloqueado_hasta", "actualizado_en"])
        return False, 0
    segundos_restantes = int((intento.bloqueado_hasta - timezone.now()).total_seconds())
    minutos = max((segundos_restantes + 59) // 60, 1)
    return True, minutos


def _limpiar_intentos_login_usuario(email, ip):
    IntentoLoginUsuario.objects.filter(username=email, ip=ip).delete()


def _reset_rate_limited(email, ip):
    limite = max(int(getattr(settings, "PASSWORD_RESET_HOURLY_LIMIT", 5)), 1)
    desde = timezone.now() - timedelta(hours=1)
    qs = PasswordResetAttempt.objects.filter(creado_en__gte=desde)
    if email:
        qs = qs.filter(email=email)
    if ip:
        qs = qs.filter(ip=ip)
    return qs.count() >= limite


def _generar_codigo_reset():
    return f"{secrets.randbelow(1_000_000):06d}"


def _nombre_archivo_seguro(nombre_original):
    ext = Path(nombre_original or "").suffix.lower()
    if ext not in {".pdf", ".jpg", ".jpeg", ".png"}:
        ext = ""
    return f"doc_{uuid.uuid4().hex}{ext}"[:255]


def _registrar_auditoria(request, evento, descripcion, usuario=None, datos=None):
    actor = usuario
    if actor is None and getattr(request, "user", None) and request.user.is_authenticated:
        actor = request.user
    EventoAuditoria.objects.create(
        usuario=actor,
        evento=evento[:80],
        descripcion=descripcion[:255],
        ip=_get_client_ip(request) if request else None,
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:255] if request else ""),
        datos=datos or {},
    )


def _worker_required(request):
    if not _user_is_worker(request.user):
        _registrar_auditoria(
            request,
            "acceso_denegado_panel_trabajador",
            "Intento de acceso a vista exclusiva de trabajador.",
            datos={"path": request.path},
        )
        messages.error(request, "Acceso solo para trabajadores autorizados.")
        return redirect("login_trabajador")
    return None


def _expirar_rechazos():
    ahora = timezone.now()
    vencidas = SolicitudRevision.objects.select_related("inscripcion").filter(
        estado=SolicitudRevision.Estado.RECHAZADA,
        plazo_correccion_limite__lt=ahora,
    )
    for solicitud in vencidas:
        solicitud.estado = SolicitudRevision.Estado.VENCIDA
        solicitud.inscripcion.estado = Inscripcion.Estado.CANCELADA
        solicitud.inscripcion.save(update_fields=["estado"])
        solicitud.save(update_fields=["estado"])
        NotificacionUsuario.objects.create(
            usuario=solicitud.inscripcion.usuario,
            titulo="Solicitud vencida",
            mensaje="Tu plazo de correccion vencio y perdiste el lugar en la convocatoria.",
        )


def _slots_por_dia(convocatoria):
    return convocatoria.capacidad_diaria_efectiva()


def _asignar_cita(convocatoria):
    capacidad_dia = _slots_por_dia(convocatoria)
    if capacidad_dia <= 0:
        return None

    conteo_por_fecha = {
        item["fecha_cita__date"]: item["total"]
        for item in SolicitudRevision.objects.filter(
            inscripcion__convocatoria=convocatoria,
            estado=SolicitudRevision.Estado.ACEPTADA,
            fecha_cita__isnull=False,
        )
        .values("fecha_cita__date")
        .annotate(total=Count("id"))
    }

    for dia_actual in convocatoria.fechas_recepcion():
        ocupados = conteo_por_fecha.get(dia_actual, 0)
        if ocupados < capacidad_dia:
            hora_inicio = convocatoria.hora_recepcion_inicio or time(9, 0)
            inicio_dia = datetime.combine(dia_actual, hora_inicio)
            duracion_cita = max(int(convocatoria.duracion_cita_minutos or 10), 1)
            fecha_cita = inicio_dia + timedelta(minutes=ocupados * duracion_cita)
            return timezone.make_aware(fecha_cita)

    convocatoria.activa = False
    convocatoria.save(update_fields=["activa"])
    return None


def _asignar_trabajador_para_solicitud():
    perfiles = list(
        TrabajadorPerfil.objects.select_related("usuario", "area").filter(
            activo=True,
            usuario__is_active=True,
        )
    )
    if not perfiles:
        return None, None

    pendientes_por_worker = {
        item["trabajador_asignado"]: item["total"]
        for item in SolicitudRevision.objects.filter(
            estado=SolicitudRevision.Estado.PENDIENTE,
            trabajador_asignado__isnull=False,
        )
        .values("trabajador_asignado")
        .annotate(total=Count("id"))
    }

    carga_minima = min(pendientes_por_worker.get(perfil.usuario_id, 0) for perfil in perfiles)
    candidatos = [perfil for perfil in perfiles if pendientes_por_worker.get(perfil.usuario_id, 0) == carga_minima]
    elegido = random.choice(candidatos)
    return elegido.usuario, elegido.area


def _documentos_base_catalogo():
    return DocumentoCatalogo.objects.filter(codigo__in=DOCUMENTOS_BASE_CODIGOS).order_by("orden", "nombre")


def _requisitos_documentales_para_convocatoria(convocatoria):
    configurados = list(
        ConvocatoriaDocumentoConfiguracion.objects.select_related("documento")
        .filter(convocatoria=convocatoria)
        .order_by("documento__orden", "documento__nombre")
    )
    if configurados:
        return [
            {
                "documento": item.documento,
                "codigo": item.documento.codigo,
                "nombre": item.documento.nombre,
                "descripcion": item.documento.descripcion,
                "copias": int(item.copias or 1),
                "requiere_original": bool(item.requiere_original),
                "mensaje": item.mensaje_usuario,
            }
            for item in configurados
        ]

    requeridos = convocatoria.documentos_requeridos.all().order_by("orden", "nombre")
    if requeridos.exists():
        return [
            {
                "documento": doc,
                "codigo": doc.codigo,
                "nombre": doc.nombre,
                "descripcion": doc.descripcion,
                "copias": 1,
                "requiere_original": False,
                "mensaje": "Entregar 1 copia",
            }
            for doc in requeridos
        ]

    return [
        {
            "documento": doc,
            "codigo": doc.codigo,
            "nombre": doc.nombre,
            "descripcion": doc.descripcion,
            "copias": 1,
            "requiere_original": False,
            "mensaje": "Entregar 1 copia",
        }
        for doc in _documentos_base_catalogo()
    ]


def _documentos_requeridos_para_convocatoria(convocatoria):
    return [item["documento"] for item in _requisitos_documentales_para_convocatoria(convocatoria)]


def _build_documentos_snapshot(usuario, convocatoria=None):
    docs_por_tipo = {
        doc.tipo: doc for doc in DocumentoUsuario.objects.filter(usuario=usuario)
    }
    if convocatoria is None:
        requeridos = list(
            DocumentoCatalogo.objects.filter(codigo__in=docs_por_tipo.keys()).order_by("orden", "nombre")
        )
    else:
        requeridos = _documentos_requeridos_para_convocatoria(convocatoria)

    snapshot = []
    for requerido in requeridos:
        doc = docs_por_tipo.get(requerido.codigo)
        if not doc or not doc.tiene_archivo:
            continue
        mime = doc.archivo_mime or mimetypes.guess_type(doc.archivo_nombre)[0] or "application/octet-stream"
        snapshot.append(
            {
                "tipo": doc.tipo,
                "nombre": requerido.nombre,
                "archivo_nombre": doc.archivo_nombre,
                "archivo_mime": mime,
                "archivo_b64": base64.b64encode(bytes(doc.archivo_binario)).decode("ascii"),
                "fecha_carga": doc.fecha_carga.isoformat() if doc.fecha_carga else "",
            }
        )
    return snapshot


def _worker_can_access_request(user, solicitud):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return solicitud.trabajador_asignado_id == user.id


def _get_snapshot_item_or_404(solicitud, indice):
    documentos = solicitud.documentos_snapshot or []
    if indice < 0 or indice >= len(documentos):
        raise Http404("Documento no encontrado en el snapshot.")
    return documentos[indice]


def home_view(request):
    return render(request, "convocatorias/home.html")


def admin_logout_redirect_view(request):
    """
    Cierra cualquier sesión activa (usuario final o trabajador) y redirige
    al login del panel de administrador. Así se evita que Django muestre
    la tarjeta sin formulario cuando ya hay una sesión abierta.
    """
    if request.user.is_authenticated:
        logout(request)
    return redirect("/Direcion-del-desarrollo-economico-sostenible/login/")


def login_view(request):
    if request.user.is_authenticated:
        logout(request)

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        ip = _get_client_ip(request)

        bloqueado, minutos = _intento_login_usuario_bloqueado(email, ip)
        if bloqueado:
            _registrar_auditoria(
                request,
                "login_usuario_bloqueado",
                "Intento de acceso de usuario bloqueado temporalmente.",
                datos={"email": email, "minutos_restantes": minutos},
            )
            messages.error(
                request,
                f"Cuenta temporalmente bloqueada por intentos fallidos. Intenta de nuevo en {minutos} minuto(s).",
            )
            return render(request, "convocatorias/login.html")

        user = authenticate(request, username=email, password=password)
        if user is not None and _user_is_final(user):
            _limpiar_intentos_login_usuario(email, ip)
            login(request, user)
            request.session["user_last_activity"] = timezone.now().timestamp()
            _registrar_auditoria(
                request,
                "login_usuario_exitoso",
                "Inicio de sesion de usuario final.",
                usuario=user,
            )
            return redirect("lista_convocatorias")
        if user is not None and _user_is_worker(user):
            _registrar_auditoria(
                request,
                "login_usuario_rol_incorrecto",
                "Intento de trabajador en login de usuario final.",
                usuario=user,
                datos={"email": email},
            )
            messages.error(request, "Tu cuenta es de trabajador. Usa el acceso de trabajador.")
            return redirect("login_trabajador")
        if user is not None and user.is_superuser:
            _registrar_auditoria(
                request,
                "login_usuario_admin_redirigido",
                "Intento de administrador en login de usuario final.",
                usuario=user,
                datos={"email": email},
            )
            messages.error(request, "Tu cuenta es de administrador. Accede desde el panel admin.")
            return redirect("/Direcion-del-desarrollo-economico-sostenible/login/")
        _registrar_fallo_login_usuario(email, ip)
        _registrar_auditoria(
            request,
            "login_usuario_fallido",
            "Credenciales invalidas en login de usuario final.",
            datos={"email": email},
        )
        messages.error(request, "Credenciales incorrectas. Verifica tu correo y contrasena.")

    return render(request, "convocatorias/login.html")


def login_trabajador_view(request):
    if request.user.is_authenticated:
        logout(request)

    form = TrabajadorLoginForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        password = form.cleaned_data["password"]
        ip = _get_client_ip(request)

        bloqueado, minutos = _intento_login_trabajador_bloqueado(email, ip)
        if bloqueado:
            _registrar_auditoria(
                request,
                "login_trabajador_bloqueado",
                "Intento de acceso de trabajador bloqueado temporalmente.",
                datos={"email": email, "minutos_restantes": minutos},
            )
            messages.error(
                request,
                f"Cuenta temporalmente bloqueada por intentos fallidos. Intenta de nuevo en {minutos} minuto(s).",
            )
            return render(request, "convocatorias/login_trabajador.html", {"form": form})

        user = authenticate(request, username=email, password=password)
        if user is None or not hasattr(user, "trabajador_perfil") or not user.trabajador_perfil.activo:
            _registrar_fallo_login_trabajador(email, ip)
            _registrar_auditoria(
                request,
                "login_trabajador_fallido",
                "Credenciales invalidas o rol no autorizado para trabajador.",
                datos={"email": email},
            )
            messages.error(request, "Credenciales incorrectas o usuario sin rol de trabajador.")
            return render(request, "convocatorias/login_trabajador.html", {"form": form})

        _limpiar_intentos_login_trabajador(email, ip)
        login(request, user)
        request.session["worker_last_activity"] = timezone.now().timestamp()
        _registrar_auditoria(
            request,
            "login_trabajador_exitoso",
            "Inicio de sesion de trabajador.",
            usuario=user,
        )
        return redirect("dashboard_trabajador")

    return render(request, "convocatorias/login_trabajador.html", {"form": form})


def registro_view(request):
    if request.user.is_authenticated:
        # Si hay una sesion activa (usuario/trabajador/admin), cerrar para mostrar registro limpio.
        logout(request)
    form = RegistroForm(request.POST or None)
    if request.method == "POST":
        ip = _get_client_ip(request)
        desde = timezone.now() - timedelta(hours=1)
        intentos_ip = EventoAuditoria.objects.filter(
            evento="registro_usuario",
            ip=ip,
            fecha__gte=desde,
        ).count()
        if intentos_ip >= 5:
            messages.error(request, "Demasiados registros desde esta IP. Intenta más tarde.")
            return render(request, "convocatorias/registro.html", {"form": form})
        acepta_terminos = request.POST.get("acepta_terminos") == "on"
        if not acepta_terminos:
            messages.error(
                request,
                "Debes aceptar los terminos y condiciones para crear una cuenta.",
            )
            return redirect("login")
        if form.is_valid():
            user = form.save()
            login(request, user)
            request.session["user_last_activity"] = timezone.now().timestamp()
            _registrar_auditoria(
                request,
                "registro_usuario",
                "Registro exitoso de usuario final.",
                usuario=user,
            )
            messages.success(request, "Cuenta creada correctamente.")
            return redirect("lista_convocatorias")
        messages.error(request, "Revisa los datos del formulario.")
    return render(request, "convocatorias/registro.html", {"form": form})


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        _registrar_auditoria(request, "logout", "Cierre de sesion.", usuario=request.user)
    logout(request)
    return redirect("login")


@login_required
def lista_convocatorias(request):
    guard = _final_user_required(request)
    if guard:
        return guard
    convocatorias = (
        Convocatoria.objects.filter(activa=True)
        .annotate(
            inscritos=Count(
                "inscripciones",
                filter=Q(inscripciones__estado=Inscripcion.Estado.ACTIVA),
            )
        )
        .order_by("-fecha_publicacion")
    )
    for convocatoria in convocatorias:
        if convocatoria.cupo_maximo <= 0:
            convocatoria.cupos_disponibles = 0
            convocatoria.estado_cupo = "llena"
        else:
            convocatoria.cupos_disponibles = max(convocatoria.cupo_maximo - convocatoria.inscritos, 0)
            if convocatoria.cupos_disponibles == 0:
                convocatoria.estado_cupo = "llena"
            elif convocatoria.cupos_disponibles <= 5:
                convocatoria.estado_cupo = "pocos"
            else:
                convocatoria.estado_cupo = "disponible"
    return render(request, "convocatorias/lista_convocatorias.html", {"convocatorias": convocatorias})


@login_required
def detalle_convocatoria(request, id):
    guard = _final_user_required(request)
    if guard:
        return guard
    convocatoria = get_object_or_404(Convocatoria, id=id)
    requeridos = _requisitos_documentales_para_convocatoria(convocatoria)
    tipos_documento = set(
        DocumentoUsuario.objects.filter(
            usuario=request.user,
            archivo_tamano__gt=0,
        ).values_list("tipo", flat=True)
    )
    documentos_requeridos = []
    for requerido in requeridos:
        documentos_requeridos.append(
            {
                "nombre": requerido["nombre"],
                "completo": requerido["codigo"] in tipos_documento,
                "copias": requerido["copias"],
                "requiere_original": requerido["requiere_original"],
                "mensaje": requerido["mensaje"],
            }
        )
    faltantes = [doc["nombre"] for doc in documentos_requeridos if not doc["completo"]]
    documentos_completos = len(faltantes) == 0
    mensajes_documentos = [doc["mensaje"] for doc in documentos_requeridos]

    # ── Estado real del usuario en esta convocatoria ──────────────────────────
    inscripcion_activa = (
        Inscripcion.objects.filter(
            convocatoria=convocatoria,
            usuario=request.user,
            estado=Inscripcion.Estado.ACTIVA,
        )
        .select_related("solicitud_revision")
        .first()
    )

    estado_inscripcion = None  # None = sin inscripcion activa
    if inscripcion_activa:
        solicitud_actual = getattr(inscripcion_activa, "solicitud_revision", None)
        estado_inscripcion = solicitud_actual.estado if solicitud_actual else "sin_solicitud"

    # ── ¿Convocatoria llena? ──────────────────────────────────────────────────
    inscritos_activos = convocatoria.inscripciones.filter(
        estado=Inscripcion.Estado.ACTIVA
    ).count()
    convocatoria_llena = (
        convocatoria.cupo_maximo > 0 and inscritos_activos >= convocatoria.cupo_maximo
    )

    return render(
        request,
        "convocatorias/detalle_convocatoria.html",
        {
            "convocatoria": convocatoria,
            "documentos_requeridos": documentos_requeridos,
            "documentos_completos": documentos_completos,
            "documentos_faltantes_texto": ", ".join(faltantes),
            "mensajes_documentos": mensajes_documentos,
            # Estado del usuario en esta convocatoria
            "estado_inscripcion": estado_inscripcion,
            "convocatoria_llena": convocatoria_llena,
        },
    )


@require_POST
@login_required
def unirse_convocatoria_view(request, id):
    guard = _final_user_required(request)
    if guard:
        return guard
    convocatoria = get_object_or_404(Convocatoria, id=id)
    requeridos = _documentos_requeridos_para_convocatoria(convocatoria)

    docs = DocumentoUsuario.objects.filter(usuario=request.user, archivo_tamano__gt=0)
    docs_por_tipo = {doc.tipo: doc for doc in docs}
    faltantes = [req.nombre for req in requeridos if req.codigo not in docs_por_tipo]
    if faltantes:
        messages.error(request, f"Debes cargar tus documentos antes de unirte: {', '.join(faltantes)}")
        return redirect("zona_usuario")

    inscripcion = Inscripcion.objects.filter(
        convocatoria=convocatoria,
        usuario=request.user,
        estado=Inscripcion.Estado.ACTIVA,
    ).first()

    # ── BLOQUEO: ya inscrito con solicitud activa ─────────────────────────────
    if inscripcion is not None:
        solicitud_existente = getattr(inscripcion, "solicitud_revision", None)
        try:
            solicitud_existente = inscripcion.solicitud_revision
        except SolicitudRevision.DoesNotExist:
            solicitud_existente = None

        if solicitud_existente and solicitud_existente.estado in [
            SolicitudRevision.Estado.PENDIENTE,
            SolicitudRevision.Estado.ACEPTADA,
        ]:
            messages.error(
                request,
                "Ya tienes una solicitud activa en esta convocatoria. "
                "No puedes inscribirte mas de una vez.",
            )
            return redirect("detalle_convocatoria", id=convocatoria.id)

        # Si la solicitud existe pero fue rechazada sin reenvio permitido
        if solicitud_existente and solicitud_existente.estado == SolicitudRevision.Estado.RECHAZADA:
            if solicitud_existente.reenvios > 0 or not solicitud_existente.plazo_correccion_limite:
                messages.error(
                    request,
                    "Tu solicitud fue rechazada sin posibilidad de reenvio. "
                    "No puedes inscribirte nuevamente en esta convocatoria.",
                )
                return redirect("detalle_convocatoria", id=convocatoria.id)
    # ─────────────────────────────────────────────────────────────────────────

    if inscripcion is None:
        try:
            with transaction.atomic():
                convocatoria = Convocatoria.objects.select_for_update().get(pk=convocatoria.pk)
                if not convocatoria.activa:
                    messages.error(request, "La convocatoria no esta activa.")
                    return redirect("detalle_convocatoria", id=convocatoria.id)
                if convocatoria.cupo_maximo <= 0:
                    messages.error(
                        request,
                        "La convocatoria no tiene cupo de citas configurado. Verifica las fechas y capacidad diaria.",
                    )
                    return redirect("detalle_convocatoria", id=convocatoria.id)
                if convocatoria.cupo_maximo > 0:
                    inscritos = convocatoria.inscripciones.filter(
                        estado=Inscripcion.Estado.ACTIVA
                    ).count()
                    if inscritos >= convocatoria.cupo_maximo:
                        messages.error(request, "La convocatoria esta llena.")
                        return redirect("detalle_convocatoria", id=convocatoria.id)
                inscripcion = Inscripcion.objects.create(
                    convocatoria=convocatoria,
                    usuario=request.user,
                    estado=Inscripcion.Estado.ACTIVA,
                    ip_registro=_get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
                )
        except Exception as exc:
            _registrar_auditoria(
                request,
                "error_registro_convocatoria",
                "Error inesperado al registrar una solicitud.",
                datos={
                    "convocatoria_id": convocatoria.id,
                    "error": exc.__class__.__name__,
                },
            )
            messages.error(request, "No fue posible registrar tu solicitud. Intenta nuevamente.")
            return redirect("detalle_convocatoria", id=convocatoria.id)

    solicitud, created = SolicitudRevision.objects.get_or_create(inscripcion=inscripcion)
    trabajador_asignado, area_asignada = _asignar_trabajador_para_solicitud()
    if not trabajador_asignado:
        messages.error(request, "No hay trabajadores activos para revisar solicitudes.")
        return redirect("detalle_convocatoria", id=convocatoria.id)

    if solicitud.estado == SolicitudRevision.Estado.RECHAZADA and solicitud.plazo_correccion_limite:
        if solicitud.plazo_correccion_limite < timezone.now():
            solicitud.estado = SolicitudRevision.Estado.VENCIDA
            solicitud.inscripcion.estado = Inscripcion.Estado.CANCELADA
            solicitud.inscripcion.save(update_fields=["estado"])
            solicitud.save(update_fields=["estado"])
            messages.error(request, "Tu plazo de correccion vencio. Debes iniciar un nuevo proceso.")
            return redirect("detalle_convocatoria", id=convocatoria.id)
        solicitud.reenvios += 1

    solicitud.estado = SolicitudRevision.Estado.PENDIENTE
    solicitud.fecha_envio = timezone.now()
    solicitud.motivo_rechazo = ""
    solicitud.plazo_correccion_limite = None
    solicitud.fecha_revision = None
    solicitud.revisado_por = None
    solicitud.trabajador_asignado = trabajador_asignado
    solicitud.area_asignada = area_asignada
    solicitud.documentos_snapshot = _build_documentos_snapshot(request.user, convocatoria=convocatoria)
    solicitud.save()
    _registrar_auditoria(
        request,
        "solicitud_enviada",
        "Solicitud enviada a revision.",
        datos={
            "convocatoria_id": convocatoria.id,
            "convocatoria_titulo": convocatoria.titulo,
            "solicitud_id": solicitud.id,
        },
    )

    NotificacionUsuario.objects.create(
        usuario=request.user,
        titulo="Solicitud enviada",
        mensaje=f"Tu documentacion fue enviada para revision en la convocatoria {convocatoria.titulo}.",
    )

    if created:
        messages.success(request, "Te uniste a la convocatoria. Tu solicitud quedo en pendiente de revision.")
    else:
        messages.success(request, "Solicitud reenviada correctamente para revision.")
    return redirect("detalle_convocatoria", id=convocatoria.id)


@login_required
def dashboard_trabajador_view(request):
    guard = _worker_required(request)
    if guard:
        return guard

    _expirar_rechazos()

    form = FiltroTrabajadorForm(request.GET or None)
    solicitudes = SolicitudRevision.objects.select_related(
        "inscripcion__convocatoria",
        "inscripcion__convocatoria__area",
        "inscripcion__usuario",
        "revisado_por",
        "trabajador_asignado",
        "area_asignada",
    ).order_by("-fecha_envio")

    if not request.user.is_superuser:
        solicitudes = solicitudes.filter(trabajador_asignado=request.user)

    if form.is_valid():
        area = form.cleaned_data.get("area")
        convocatoria = form.cleaned_data.get("convocatoria")
        fecha = form.cleaned_data.get("fecha")
        estado = form.cleaned_data.get("estado")
        if area:
            solicitudes = solicitudes.filter(inscripcion__convocatoria__area=area)
        if convocatoria:
            solicitudes = solicitudes.filter(inscripcion__convocatoria=convocatoria)
        if fecha:
            solicitudes = solicitudes.filter(fecha_envio__date=fecha)
        if estado:
            solicitudes = solicitudes.filter(estado=estado)

    pendientes = solicitudes.filter(estado=SolicitudRevision.Estado.PENDIENTE)
    aceptadas = solicitudes.filter(estado=SolicitudRevision.Estado.ACEPTADA)
    rechazadas = solicitudes.filter(estado__in=[SolicitudRevision.Estado.RECHAZADA, SolicitudRevision.Estado.VENCIDA])

    context = {
        "form": form,
        "convocatorias_activas": Convocatoria.objects.filter(activa=True).count(),
        "pendientes_count": pendientes.count(),
        "aceptadas_count": aceptadas.count(),
        "rechazadas_count": rechazadas.count(),
        "pendientes": pendientes[:100],
        "aceptadas": aceptadas[:100],
        "rechazadas": rechazadas[:100],
        "pendientes_total": pendientes.count(),
        "aceptadas_total": aceptadas.count(),
        "rechazadas_total": rechazadas.count(),
    }
    return render(request, "convocatorias/dashboard_trabajador.html", context)


@login_required
def revisar_solicitud_trabajador_view(request, solicitud_id):
    guard = _worker_required(request)
    if guard:
        return guard

    solicitud = get_object_or_404(
        SolicitudRevision.objects.select_related("inscripcion__convocatoria", "inscripcion__usuario"),
        id=solicitud_id,
    )
    if not request.user.is_superuser and solicitud.trabajador_asignado_id != request.user.id:
        _registrar_auditoria(
            request,
            "acceso_denegado_revision",
            "Intento de acceso a solicitud no asignada.",
            datos={"solicitud_id": solicitud.id},
        )
        messages.error(request, "No tienes permiso para revisar esta solicitud.")
        return redirect("dashboard_trabajador")
    usuario = solicitud.inscripcion.usuario
    perfil = PerfilUsuario.objects.filter(usuario=usuario).first()
    documentos_revision = solicitud.documentos_snapshot or []
    if not documentos_revision:
        # Compatibilidad para solicitudes antiguas sin snapshot: congelar desde la primera consulta.
        documentos_revision = _build_documentos_snapshot(usuario, solicitud.inscripcion.convocatoria)
        solicitud.documentos_snapshot = documentos_revision
        solicitud.save(update_fields=["documentos_snapshot"])
    documentos_revision = [
        {
            **doc,
            "archivo_url": reverse(
                "ver_documento_snapshot_trabajador",
                kwargs={"solicitud_id": solicitud.id, "indice": idx},
            ),
        }
        for idx, doc in enumerate(documentos_revision)
    ]

    rechazo_form = RevisionRechazoForm(request.POST or None)

    if request.method == "POST":
        accion = request.POST.get("accion")
        convocatoria = solicitud.inscripcion.convocatoria

        # ── GUARD: bloquear re-procesamiento de solicitudes ya cerradas ───────
        estados_cerrados = [
            SolicitudRevision.Estado.ACEPTADA,
            SolicitudRevision.Estado.VENCIDA,
        ]
        if solicitud.estado in estados_cerrados:
            messages.error(
                request,
                f"Esta solicitud ya fue procesada ({solicitud.get_estado_display()}). "
                "No se puede modificar.",
            )
            return redirect("dashboard_trabajador")
        # ─────────────────────────────────────────────────────────────────────

        if accion == "aceptar":
            if convocatoria.cupo_maximo > 0:
                inscritos = convocatoria.inscripciones.filter(
                    estado=Inscripcion.Estado.ACTIVA
                ).count()
                if inscritos > convocatoria.cupo_maximo:
                    messages.error(
                        request,
                        "El cupo de la convocatoria ya fue excedido. "
                        "No se puede aceptar hasta liberar espacios.",
                    )
                    return redirect("revisar_solicitud_trabajador", solicitud_id=solicitud.id)
            fecha_cita = _asignar_cita(convocatoria)
            if not fecha_cita:
                messages.error(request, "No hay espacios disponibles para asignar cita en esta convocatoria.")
                return redirect("revisar_solicitud_trabajador", solicitud_id=solicitud.id)

            siguiente_ficha = (
                SolicitudRevision.objects.filter(
                    inscripcion__convocatoria=convocatoria,
                    estado=SolicitudRevision.Estado.ACEPTADA,
                )
                .aggregate(max_ficha=Max("numero_ficha"))
                .get("max_ficha")
                or 0
            ) + 1

            solicitud.estado = SolicitudRevision.Estado.ACEPTADA
            solicitud.fecha_revision = timezone.now()
            solicitud.revisado_por = request.user
            solicitud.motivo_rechazo = ""
            solicitud.plazo_correccion_limite = None
            solicitud.fecha_cita = fecha_cita
            solicitud.numero_ficha = siguiente_ficha
            solicitud.save()
            _registrar_auditoria(
                request,
                "solicitud_aceptada",
                "Solicitud aceptada por trabajador.",
                datos={
                    "solicitud_id": solicitud.id,
                    "convocatoria_id": convocatoria.id,
                    "usuario_id": usuario.id,
                    "numero_ficha": siguiente_ficha,
                },
            )

            NotificacionUsuario.objects.create(
                usuario=usuario,
                titulo="Solicitud aceptada",
                mensaje=(
                    f"Tu documentacion fue aceptada. Cita: {fecha_cita.strftime('%d/%m/%Y %H:%M')}. "
                    f"Ficha: {siguiente_ficha}. Si llegas tarde, la cita puede cancelarse."
                ),
            )
            messages.success(request, "Solicitud aceptada y cita asignada correctamente.")
            return redirect("dashboard_trabajador")

        if accion == "rechazar" and rechazo_form.is_valid():
            permitir_reenvio = rechazo_form.cleaned_data.get("permitir_reenvio", False)
            if solicitud.reenvios > 0:
                permitir_reenvio = False
            solicitud.fecha_revision = timezone.now()
            solicitud.revisado_por = request.user
            solicitud.motivo_rechazo = rechazo_form.cleaned_data["motivo_rechazo"]
            solicitud.fecha_cita = None
            solicitud.numero_ficha = None

            if permitir_reenvio:
                plazo_dias = rechazo_form.cleaned_data.get("plazo_correccion_dias") or 2
                solicitud.estado = SolicitudRevision.Estado.RECHAZADA
                solicitud.plazo_correccion_limite = timezone.now() + timedelta(days=plazo_dias)
                solicitud.save()
                _registrar_auditoria(
                    request,
                    "solicitud_rechazada_con_reenvio",
                    "Solicitud rechazada con posibilidad de reenviar.",
                    datos={
                        "solicitud_id": solicitud.id,
                        "convocatoria_id": convocatoria.id,
                        "usuario_id": usuario.id,
                        "plazo_dias": plazo_dias,
                    },
                )
                NotificacionUsuario.objects.create(
                    usuario=usuario,
                    titulo="Solicitud rechazada",
                    mensaje=(
                        "Tu solicitud fue rechazada. Motivo: "
                        f"{solicitud.motivo_rechazo}. "
                        f"Tienes {plazo_dias} dias para corregir y reenviar desde Perfil y documentos."
                    ),
                )
                messages.success(request, "Solicitud rechazada con opcion de reenvio.")
            else:
                solicitud.estado = SolicitudRevision.Estado.VENCIDA
                solicitud.plazo_correccion_limite = None
                solicitud.save()
                solicitud.inscripcion.estado = Inscripcion.Estado.CANCELADA
                solicitud.inscripcion.save(update_fields=["estado"])
                _registrar_auditoria(
                    request,
                    "solicitud_rechazada_definitiva",
                    "Solicitud rechazada de forma definitiva.",
                    datos={
                        "solicitud_id": solicitud.id,
                        "convocatoria_id": convocatoria.id,
                        "usuario_id": usuario.id,
                    },
                )
                NotificacionUsuario.objects.create(
                    usuario=usuario,
                    titulo="Solicitud rechazada sin reenvio",
                    mensaje=(
                        "Tu solicitud fue rechazada de forma definitiva. Motivo: "
                        f"{solicitud.motivo_rechazo}."
                    ),
                )
                messages.success(request, "Solicitud rechazada de forma definitiva.")
            return redirect("dashboard_trabajador")

    return render(
        request,
        "convocatorias/revisar_solicitud_trabajador.html",
        {
            "solicitud": solicitud,
            "usuario_objetivo": usuario,
            "perfil": perfil,
            "documentos_revision": documentos_revision,
            "rechazo_form": rechazo_form,
        },
    )


@login_required
def zona_usuario_view(request):
    guard = _final_user_required(request)
    if guard:
        return guard
    perfil = PerfilUsuario.objects.filter(usuario=request.user).first()
    documentos_catalogo = list(DocumentoCatalogo.objects.filter(activo=True).order_by("orden", "nombre"))
    if not documentos_catalogo:
        documentos_catalogo = list(_documentos_base_catalogo())

    perfil_form = PerfilUsuarioForm(instance=perfil)
    cambio_password_form = CambiarContrasenaForm(request.user)
    subida_documento_form = SubidaDocumentoForm(documentos_disponibles=documentos_catalogo)

    if request.method == "POST":
        accion = request.POST.get("accion")

        if accion == "guardar_informacion":
            perfil_form = PerfilUsuarioForm(request.POST, instance=perfil)
            if perfil_form.is_valid():
                perfil_guardado = perfil_form.save(commit=False)
                perfil_guardado.usuario = request.user
                perfil_guardado.save()
                _registrar_auditoria(
                    request,
                    "perfil_actualizado",
                    "Actualizacion de informacion personal.",
                )
                messages.success(request, "Informacion guardada correctamente.")
                return redirect("zona_usuario")

        elif accion == "subir_documento":
            subida_documento_form = SubidaDocumentoForm(
                request.POST,
                request.FILES,
                documentos_disponibles=documentos_catalogo,
            )
            if subida_documento_form.is_valid():
                try:
                    archivo_subido = subida_documento_form.cleaned_data["archivo"]
                    archivo_nombre = _nombre_archivo_seguro(archivo_subido.name)
                    archivo_mime = (
                        getattr(archivo_subido, "content_type", "")
                        or mimetypes.guess_type(archivo_nombre)[0]
                        or "application/octet-stream"
                    )
                    archivo_binario = archivo_subido.read()
                    DocumentoUsuario.objects.update_or_create(
                        usuario=request.user,
                        tipo=subida_documento_form.cleaned_data["tipo"],
                        defaults={
                            "archivo_nombre": archivo_nombre,
                            "archivo_mime": archivo_mime,
                            "archivo_tamano": len(archivo_binario),
                            "archivo_binario": archivo_binario,
                            "estado": DocumentoUsuario.Estado.ACEPTADO,
                        },
                    )
                    _registrar_auditoria(
                        request,
                        "documento_cargado",
                        "Carga o reemplazo de documento de usuario.",
                        datos={"tipo_documento": subida_documento_form.cleaned_data["tipo"]},
                    )
                except Exception:
                    messages.error(request, "No se pudo subir el documento. Intente nuevamente.")
                    return redirect("zona_usuario")

                messages.success(request, "Documento cargado correctamente.")
                return redirect("zona_usuario")

        elif accion == "eliminar_documento":
            tipo = request.POST.get("tipo", "")
            if tipo:
                DocumentoUsuario.objects.filter(usuario=request.user, tipo=tipo).delete()
                _registrar_auditoria(
                    request,
                    "documento_eliminado",
                    "Eliminacion de documento de usuario.",
                    datos={"tipo_documento": tipo},
                )
                messages.success(request, "Documento eliminado correctamente.")
            return redirect("zona_usuario")

        elif accion == "cambiar_contrasena":
            cambio_password_form = CambiarContrasenaForm(request.user, request.POST)
            if cambio_password_form.is_valid():
                request.user.set_password(cambio_password_form.cleaned_data["password_nueva"])
                request.user.save(update_fields=["password"])
                update_session_auth_hash(request, request.user)
                _registrar_auditoria(
                    request,
                    "contrasena_actualizada",
                    "Cambio de contrasena desde zona de usuario.",
                )
                messages.success(request, "Contrasena actualizada correctamente.")
                return redirect("zona_usuario")

        elif accion == "reenviar_solicitud":
            solicitud_id = request.POST.get("solicitud_id")
            solicitud = SolicitudRevision.objects.select_related("inscripcion__convocatoria").filter(
                id=solicitud_id,
                inscripcion__usuario=request.user,
            ).first()
            if not solicitud:
                messages.error(request, "No se encontro la solicitud a reenviar.")
                return redirect("zona_usuario")
            if solicitud.estado != SolicitudRevision.Estado.RECHAZADA:
                messages.error(request, "Solo puedes reenviar solicitudes rechazadas con reenvio permitido.")
                return redirect("zona_usuario")
            if not solicitud.plazo_correccion_limite or solicitud.plazo_correccion_limite < timezone.now():
                solicitud.estado = SolicitudRevision.Estado.VENCIDA
                solicitud.inscripcion.estado = Inscripcion.Estado.CANCELADA
                solicitud.inscripcion.save(update_fields=["estado"])
                solicitud.save(update_fields=["estado"])
                messages.error(request, "Tu plazo de correccion ya vencio.")
                return redirect("zona_usuario")

            requeridos = _documentos_requeridos_para_convocatoria(solicitud.inscripcion.convocatoria)
            docs_por_tipo = {
                doc.tipo: doc
                for doc in DocumentoUsuario.objects.filter(usuario=request.user, archivo_tamano__gt=0)
            }
            faltantes = [req.nombre for req in requeridos if req.codigo not in docs_por_tipo]
            if faltantes:
                messages.error(request, f"Aun faltan documentos para reenviar: {', '.join(faltantes)}")
                return redirect("zona_usuario")

            trabajador_asignado, area_asignada = _asignar_trabajador_para_solicitud()
            if not trabajador_asignado:
                messages.error(request, "No hay trabajadores activos para revisar solicitudes.")
                return redirect("zona_usuario")

            solicitud.reenvios += 1
            solicitud.estado = SolicitudRevision.Estado.PENDIENTE
            solicitud.fecha_envio = timezone.now()
            solicitud.motivo_rechazo = ""
            solicitud.plazo_correccion_limite = None
            solicitud.fecha_revision = None
            solicitud.revisado_por = None
            solicitud.trabajador_asignado = trabajador_asignado
            solicitud.area_asignada = area_asignada
            solicitud.documentos_snapshot = _build_documentos_snapshot(
                request.user,
                convocatoria=solicitud.inscripcion.convocatoria,
            )
            solicitud.save()
            _registrar_auditoria(
                request,
                "solicitud_reenviada",
                "Solicitud reenviada por el usuario.",
                datos={
                    "solicitud_id": solicitud.id,
                    "convocatoria_id": solicitud.inscripcion.convocatoria.id,
                },
            )

            NotificacionUsuario.objects.create(
                usuario=request.user,
                titulo="Solicitud reenviada",
                mensaje=(
                    f"Tu solicitud de la convocatoria {solicitud.inscripcion.convocatoria.titulo} "
                    "se reenvio para nueva revision."
                ),
            )
            messages.success(request, "Solicitud reenviada correctamente. Ahora aparece como pendiente.")
            return redirect("zona_usuario")

        elif accion == "vaciar_notificaciones":
            NotificacionUsuario.objects.filter(usuario=request.user).delete()
            messages.success(request, "Notificaciones eliminadas correctamente.")
            return redirect("zona_usuario")

    documentos_usuario = {
        documento.tipo: documento
        for documento in DocumentoUsuario.objects.filter(usuario=request.user, archivo_tamano__gt=0)
    }

    documentos = []
    for doc_requerido in documentos_catalogo:
        documento = documentos_usuario.get(doc_requerido.codigo)
        if documento and documento.tiene_archivo:
            archivo_nombre = documento.archivo_nombre
            archivo_extension = archivo_nombre.rsplit(".", 1)[-1].lower() if "." in archivo_nombre else ""
            estado_etiqueta = "Cargado"
            estado_texto = "Documento cargado por el usuario."
            archivo_url = reverse("ver_documento_usuario", kwargs={"documento_id": documento.id})
        else:
            archivo_nombre = ""
            archivo_extension = ""
            archivo_url = ""
            estado_etiqueta = "Pendiente"
            estado_texto = "Documento no cargado."

        documentos.append(
            {
                "tipo": doc_requerido.codigo,
                "nombre": doc_requerido.nombre,
                "descripcion": doc_requerido.descripcion,
                "estado_etiqueta": estado_etiqueta,
                "estado_texto": estado_texto,
                "cargado": bool(archivo_url),
                "archivo_nombre": archivo_nombre,
                "archivo_extension": archivo_extension,
                "archivo_url": archivo_url,
            }
        )

    notificaciones = NotificacionUsuario.objects.filter(usuario=request.user)[:10]
    solicitudes_reenviar = (
        SolicitudRevision.objects.select_related("inscripcion__convocatoria")
        .filter(
            inscripcion__usuario=request.user,
            estado=SolicitudRevision.Estado.RECHAZADA,
            plazo_correccion_limite__gte=timezone.now(),
        )
        .order_by("-fecha_revision")[:10]
    )

    return render(
        request,
        "convocatorias/zona_usuario.html",
        {
            "perfil_form": perfil_form,
            "subida_documento_form": subida_documento_form,
            "cambio_password_form": cambio_password_form,
            "documentos": documentos,
            "max_mb_documento": SubidaDocumentoForm.MAX_MB,
            "notificaciones": notificaciones,
            "solicitudes_reenviar": solicitudes_reenviar,
        },
    )


@login_required
def gestion_documentos_view(request):
    guard = _final_user_required(request)
    if guard:
        return guard
    return render(request, "convocatorias/gestion_documentos.html")


@login_required
def verificacion_token_view(request):
    guard = _final_user_required(request)
    if guard:
        return guard
    return render(request, "convocatorias/verificacion_token.html")


@login_required
def validacion_convocatoria_view(request):
    guard = _final_user_required(request)
    if guard:
        return guard
    return render(request, "convocatorias/validacion_convocatoria.html")


@login_required
def documentos_faltantes_view(request):
    guard = _final_user_required(request)
    if guard:
        return guard
    return render(request, "convocatorias/documentos_faltantes.html")


@login_required
def documento_extra_view(request):
    guard = _final_user_required(request)
    if guard:
        return guard
    return render(request, "convocatorias/documento_extra.html")


@login_required
def registro_exitoso_view(request):
    guard = _final_user_required(request)
    if guard:
        return guard
    return render(request, "convocatorias/registro_exitoso.html")


def terminos_condiciones_view(request):
    return render(request, "convocatorias/terminos_condiciones.html")


@login_required
def ver_documento_usuario_view(request, documento_id):
    guard = _final_user_required(request)
    if guard:
        return guard
    documento = get_object_or_404(
        DocumentoUsuario,
        id=documento_id,
        usuario=request.user,
    )
    if not documento.tiene_archivo:
        raise Http404("Documento sin archivo.")

    content_type = documento.archivo_mime or mimetypes.guess_type(documento.archivo_nombre)[0] or "application/octet-stream"
    if content_type not in {"application/pdf", "image/jpeg", "image/png"}:
        content_type = "application/octet-stream"
    response = HttpResponse(bytes(documento.archivo_binario), content_type=content_type)
    response["Content-Disposition"] = f'inline; filename="{Path(documento.archivo_nombre).name}"'
    response["Cache-Control"] = "no-store, max-age=0, must-revalidate, private"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


@login_required
def ver_documento_snapshot_trabajador_view(request, solicitud_id, indice):
    solicitud = get_object_or_404(SolicitudRevision, id=solicitud_id)
    if not _worker_can_access_request(request.user, solicitud):
        _registrar_auditoria(
            request,
            "acceso_denegado_snapshot",
            "Intento de acceso a documento snapshot no autorizado.",
            datos={"solicitud_id": solicitud_id, "indice": indice},
        )
        raise Http404("Solicitud no encontrada.")

    item = _get_snapshot_item_or_404(solicitud, indice)
    b64 = item.get("archivo_b64") or ""
    if not b64:
        raise Http404("Documento snapshot sin contenido.")

    try:
        contenido = base64.b64decode(b64, validate=True)
    except Exception as exc:  # pragma: no cover - datos corruptos en DB
        raise Http404("Documento snapshot invalido.") from exc

    nombre = Path(item.get("archivo_nombre") or f"documento_{indice}").name
    content_type = item.get("archivo_mime") or mimetypes.guess_type(nombre)[0] or "application/octet-stream"
    if content_type not in {"application/pdf", "image/jpeg", "image/png"}:
        content_type = "application/octet-stream"
    response = HttpResponse(contenido, content_type=content_type)
    response["Content-Disposition"] = f'inline; filename="{nombre}"'
    response["Cache-Control"] = "no-store, max-age=0, must-revalidate, private"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


def password_reset_view(request):
    step = request.POST.get("step", "request")
    context = {"step": step}

    if request.method == "POST" and step == "request":
        email = request.POST.get("email", "").strip().lower()
        ip = _get_client_ip(request)
        context["email"] = email
        PasswordResetAttempt.objects.create(email=email or "desconocido", ip=ip)
        _registrar_auditoria(
            request,
            "password_reset_solicitado",
            "Solicitud de recuperacion de contrasena.",
            datos={"email": email},
        )
        if _reset_rate_limited(email, ip):
            messages.error(request, "Demasiados intentos. Intenta nuevamente mas tarde.")
            return render(request, "convocatorias/password_reset.html", context)

        user = get_user_model().objects.filter(username=email, is_active=True).first()
        if user and _user_is_final(user):
            codigo = _generar_codigo_reset()
            PasswordResetCode.objects.create(
                usuario=user,
                codigo="",
                codigo_hash=make_password(codigo),
            )
            asunto = "Codigo de verificacion - Convocatorias"
            mensaje = (
                "Solicitaste recuperar tu contrasena.\n\n"
                f"Codigo de verificacion: {codigo}\n"
                "Este codigo vence en pocos minutos."
            )
            try:
                send_mail(
                    asunto,
                    mensaje,
                    settings.DEFAULT_FROM_EMAIL,
                    [email],
                    fail_silently=False,
                )
            except Exception as mail_exc:
                import logging
                logging.getLogger(__name__).error(
                    "Error al enviar correo de recuperacion a %s: %s",
                    email,
                    mail_exc,
                )
                _registrar_auditoria(
                    request,
                    "error_envio_correo_reset",
                    "Fallo el envio del correo de recuperacion de contrasena.",
                    datos={"email": email, "error": str(mail_exc)},
                )
        messages.success(
            request,
            "Si el correo existe, se envio un codigo de verificacion. Revisa tu bandeja.",
        )
        context["step"] = "verify"
        return render(request, "convocatorias/password_reset.html", context)

    if request.method == "POST" and step == "verify":
        email = request.POST.get("email", "").strip().lower()
        codigo = request.POST.get("codigo", "").strip()
        password1 = request.POST.get("password1", "")
        password2 = request.POST.get("password2", "")
        context["email"] = email
        context["step"] = "verify"

        user = get_user_model().objects.filter(username=email, is_active=True).first()
        if not user or not _user_is_final(user):
            messages.error(request, "Codigo invalido o expirado.")
            return render(request, "convocatorias/password_reset.html", context)

        minutos = max(int(getattr(settings, "PASSWORD_RESET_CODE_MINUTES", 10)), 1)
        max_intentos = max(int(getattr(settings, "PASSWORD_RESET_MAX_ATTEMPTS", 5)), 1)
        desde = timezone.now() - timedelta(minutes=minutos)
        registro = (
            PasswordResetCode.objects.filter(usuario=user, usado=False, creado_en__gte=desde)
            .order_by("-creado_en")
            .first()
        )
        if not registro or not registro.codigo_coincide(codigo):
            if registro:
                registro.intentos_fallidos += 1
                if registro.intentos_fallidos >= max_intentos:
                    registro.usado = True
                registro.save(update_fields=["intentos_fallidos", "usado"])
            messages.error(request, "Codigo invalido o expirado.")
            return render(request, "convocatorias/password_reset.html", context)

        if not password1 or password1 != password2:
            messages.error(request, "Las contrasenas no coinciden.")
            return render(request, "convocatorias/password_reset.html", context)

        try:
            validate_password(password1, user)
        except ValidationError as exc:
            for error in exc.messages:
                messages.error(request, error)
            return render(request, "convocatorias/password_reset.html", context)

        user.set_password(password1)
        user.save(update_fields=["password"])
        registro.usado = True
        registro.save(update_fields=["usado"])
        _registrar_auditoria(
            request,
            "password_reset_completado",
            "Cambio de contrasena mediante codigo de recuperacion.",
            usuario=user,
            datos={"email": email},
        )
        messages.success(request, "Contrasena actualizada. Ahora puedes iniciar sesion.")
        return redirect("login")

    return render(request, "convocatorias/password_reset.html", context)
