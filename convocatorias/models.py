import mimetypes
from pathlib import Path

from django.contrib.auth.hashers import check_password
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import time, timedelta

class Area(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    descripcion = models.CharField(max_length=255, blank=True)
    activa = models.BooleanField(default=True)
    fecha_registro = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "Area"
        verbose_name_plural = "Areas"

    def __str__(self):
        return self.nombre


class Convocatoria(models.Model):
    titulo = models.CharField(max_length=200)
    area = models.ForeignKey(
        Area,
        related_name="convocatorias",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
    )

    descripcion = models.TextField(
        help_text="Descripción general de la convocatoria"
    )

    dependencia = models.CharField(
        max_length=200,
        help_text="Dependencia o dirección que convoca"
    )

    objetivo = models.TextField(
        help_text="Objetivo del programa"
    )

    dirigido_a = models.TextField(
        help_text="A quién va dirigida la convocatoria"
    )

    requisitos = models.TextField(
        help_text="Requisitos generales"
    )

    beneficios = models.TextField(
        help_text="Beneficios que ofrece el programa"
    )

    fecha_inicio = models.DateField(
        help_text="Fecha de inicio de la convocatoria (inscripciones)"
    )
    fecha_fin = models.DateField(
        help_text="Fecha fin de la convocatoria (inscripciones)"
    )
    fecha_inicio_recepcion = models.DateField(
        blank=True,
        null=True,
        help_text="Fecha de inicio para recibir documentos",
    )
    fecha_fin_recepcion = models.DateField(
        blank=True,
        null=True,
        help_text="Fecha límite para recibir documentos",
    )
    dias_recepcion = models.PositiveIntegerField(blank=True, null=True)

    lugar_recepcion = models.CharField(
        max_length=255,
        help_text="Lugar donde se reciben los documentos"
    )

    horario = models.CharField(
        max_length=100,
        help_text="Horario de atención (fijo)",
    )

    forma_entrega = models.CharField(
        max_length=200,
        help_text="Forma de entrega de documentos"
    )

    contacto = models.TextField(
        help_text="Teléfono, correo o redes oficiales"
    )

    imagen = models.ImageField(
        upload_to='convocatorias/',
        blank=True,
        null=True
    )
    documentos_requeridos = models.ManyToManyField(
        "DocumentoCatalogo",
        related_name="convocatorias",
        blank=True,
        help_text="Selecciona los documentos obligatorios para esta convocatoria.",
    )

    activa = models.BooleanField(default=True)
    fecha_publicacion = models.DateField(auto_now_add=True)
    cupo_maximo = models.PositiveIntegerField(
        default=0,
        help_text="0 = sin l\u00edmite de inscripciones"
    )
    personas_maximas_por_dia = models.PositiveIntegerField(
        default=80,
        help_text="Maximo de personas que se atenderan por dia"
    )
    hora_recepcion_inicio = models.TimeField(
        default=time(10, 0),
        help_text="Hora de inicio de recepcion documental"
    )
    hora_recepcion_fin = models.TimeField(
        default=time(14, 0),
        help_text="Hora de termino de recepcion documental"
    )
    duracion_cita_minutos = models.PositiveSmallIntegerField(
        default=10,
        help_text="Duracion de cada cita en minutos"
    )

    HORARIO_RECEPCION_FIJO = "10:00 a 14:00"

    def __str__(self):
        return self.titulo

    def fechas_recepcion(self):
        if not self.fecha_inicio_recepcion or not self.fecha_fin_recepcion:
            return []
        if self.fecha_fin_recepcion < self.fecha_inicio_recepcion:
            return []
        fechas = []
        dia_actual = self.fecha_inicio_recepcion
        while dia_actual <= self.fecha_fin_recepcion:
            fechas.append(dia_actual)
            dia_actual += timedelta(days=1)
        return fechas

    def capacidad_diaria_efectiva(self):
        if not self.personas_maximas_por_dia:
            return 0
        if not self.hora_recepcion_inicio or not self.hora_recepcion_fin:
            return int(self.personas_maximas_por_dia)
        if self.hora_recepcion_fin <= self.hora_recepcion_inicio:
            return 0
        duracion = max(int(self.duracion_cita_minutos or 10), 1)
        minutos = int(
            (self.hora_recepcion_fin.hour * 60 + self.hora_recepcion_fin.minute)
            - (self.hora_recepcion_inicio.hour * 60 + self.hora_recepcion_inicio.minute)
        )
        slots_por_horario = max(minutos // duracion, 0)
        return max(min(int(self.personas_maximas_por_dia), slots_por_horario), 0)

    def save(self, *args, **kwargs):
        hoy = timezone.localdate()
        if self.fecha_inicio and self.fecha_fin:
            self.activa = self.fecha_inicio <= hoy <= self.fecha_fin
        self.horario = self.HORARIO_RECEPCION_FIJO
        self.hora_recepcion_inicio = time(10, 0)
        self.hora_recepcion_fin = time(14, 0)
        if self.fecha_inicio_recepcion and self.fecha_fin_recepcion:
            delta = self.fecha_fin_recepcion - self.fecha_inicio_recepcion
            self.dias_recepcion = max(delta.days + 1, 0)
        else:
            self.dias_recepcion = 0
        if self.dias_recepcion and self.personas_maximas_por_dia:
            self.cupo_maximo = self.dias_recepcion * self.personas_maximas_por_dia
        else:
            self.cupo_maximo = 0
        return super().save(*args, **kwargs)

    @property
    def cupo_disponible(self):
        if self.cupo_maximo <= 0:
            return 0
        inscritos = self.inscripciones.filter(estado=Inscripcion.Estado.ACTIVA).count()
        return max(self.cupo_maximo - inscritos, 0)

    def puede_inscribir(self):
        if not self.activa:
            return False
        if self.cupo_maximo <= 0:
            return False
        return self.cupo_disponible > 0


class Inscripcion(models.Model):
    class Estado(models.TextChoices):
        ACTIVA = "activa", "Activa"
        CANCELADA = "cancelada", "Cancelada"

    convocatoria = models.ForeignKey(
        Convocatoria,
        related_name="inscripciones",
        on_delete=models.CASCADE
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="inscripciones_convocatoria",
        on_delete=models.PROTECT
    )
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.ACTIVA
    )
    fecha_registro = models.DateTimeField(default=timezone.now)
    ip_registro = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True)
    nota_admin = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["convocatoria", "usuario"],
                condition=Q(estado="activa"),
                name="uniq_inscripcion_activa_por_usuario"
            )
        ]
        indexes = [
            models.Index(fields=["convocatoria", "estado"]),
            models.Index(fields=["usuario", "estado"]),
        ]

    def clean(self):
        if not self.convocatoria.activa:
            raise ValidationError("La convocatoria no est\u00e1 activa.")
        if self.convocatoria.cupo_maximo <= 0:
            raise ValidationError("La convocatoria no tiene capacidad disponible para citas.")
        inscritos = self.convocatoria.inscripciones.filter(
            estado=Inscripcion.Estado.ACTIVA
        ).exclude(pk=self.pk).count()
        if inscritos >= self.convocatoria.cupo_maximo:
            raise ValidationError("No hay cupo disponible para esta convocatoria.")

    def save(self, *args, **kwargs):
        with transaction.atomic():
            self.full_clean()
            return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.usuario} -> {self.convocatoria} ({self.estado})"


class PerfilUsuario(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="perfil_usuario",
        on_delete=models.CASCADE
    )
    nombre_completo = models.CharField(max_length=255)
    curp = models.CharField(max_length=18)
    telefono = models.CharField(max_length=20)
    direccion = models.CharField(max_length=255)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Perfil de {self.usuario.username}"


class DocumentoUsuario(models.Model):
    class Tipo(models.TextChoices):
        IDENTIFICACION = "identificacion_oficial", "Identificacion oficial"
        CURP = "curp", "CURP"
        COMPROBANTE_DOMICILIO = "comprobante_domicilio", "Comprobante de domicilio"

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        EN_REVISION = "en_revision", "En revision"
        ACEPTADO = "aceptado", "Aceptado"
        RECHAZADO = "rechazado", "Rechazado"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="documentos_usuario",
        on_delete=models.CASCADE
    )
    tipo = models.CharField(max_length=50)
    archivo_nombre = models.CharField(max_length=255, blank=True, default="")
    archivo_mime = models.CharField(max_length=100, blank=True, default="")
    archivo_tamano = models.PositiveIntegerField(default=0)
    archivo_binario = models.BinaryField(blank=True, default=b"")
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.EN_REVISION
    )
    fecha_carga = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "tipo"],
                name="uniq_documento_por_usuario_y_tipo"
            )
        ]

    @property
    def nombre_tipo(self):
        match = DocumentoCatalogo.objects.filter(codigo=self.tipo).values_list("nombre", flat=True).first()
        if match:
            return match
        legacy = dict(self.Tipo.choices).get(self.tipo)
        if legacy:
            return legacy
        return self.tipo.replace("_", " ").strip().title()

    def __str__(self):
        return f"{self.usuario.username} - {self.nombre_tipo} ({self.get_estado_display()})"

    @property
    def tiene_archivo(self):
        return bool(self.archivo_binario)

    @property
    def extension_archivo(self):
        nombre = self.archivo_nombre or ""
        if "." not in nombre:
            return ""
        return nombre.rsplit(".", 1)[-1].lower()

    def set_archivo_desde_upload(self, upload):
        nombre = Path(upload.name).name[:255]
        contenido = upload.read()
        if hasattr(upload, "seek"):
            upload.seek(0)

        mime = getattr(upload, "content_type", "") or ""
        if not mime:
            mime = mimetypes.guess_type(nombre)[0] or "application/octet-stream"

        self.archivo_nombre = nombre
        self.archivo_mime = mime
        self.archivo_tamano = len(contenido)
        self.archivo_binario = contenido


class DocumentoCatalogo(models.Model):
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=120)
    descripcion = models.CharField(max_length=255, blank=True)
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["orden", "nombre"]
        verbose_name = "Documento del catalogo"
        verbose_name_plural = "Documentos del catalogo"

    def __str__(self):
        return self.nombre


class ConvocatoriaDocumentoConfiguracion(models.Model):
    convocatoria = models.ForeignKey(
        Convocatoria,
        related_name="documentos_configurados",
        on_delete=models.CASCADE,
    )
    documento = models.ForeignKey(
        DocumentoCatalogo,
        related_name="configuraciones_convocatoria",
        on_delete=models.CASCADE,
    )
    copias = models.PositiveSmallIntegerField(default=1)
    requiere_original = models.BooleanField(default=False)

    class Meta:
        ordering = ["documento__orden", "documento__nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["convocatoria", "documento"],
                name="uniq_config_documento_por_convocatoria",
            )
        ]
        verbose_name = "Documento requerido por convocatoria"
        verbose_name_plural = "Documentos requeridos por convocatoria"

    @property
    def mensaje_usuario(self):
        partes = []
        cantidad = int(self.copias or 0)
        if cantidad <= 1:
            partes.append("Entregar 1 copia")
        else:
            partes.append(f"Entregar {cantidad} copias")
        if self.requiere_original:
            partes.append("presentar original")
        return ", ".join(partes)

    def __str__(self):
        return f"{self.convocatoria} - {self.documento}"


class SolicitudRevision(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ACEPTADA = "aceptada", "Aceptada"
        RECHAZADA = "rechazada", "Rechazada"
        VENCIDA = "vencida", "Vencida"

    inscripcion = models.OneToOneField(
        Inscripcion,
        related_name="solicitud_revision",
        on_delete=models.CASCADE
    )
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE)
    fecha_envio = models.DateTimeField(default=timezone.now)
    fecha_revision = models.DateTimeField(blank=True, null=True)
    revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="solicitudes_revisadas",
        on_delete=models.SET_NULL,
        blank=True,
        null=True
    )
    motivo_rechazo = models.TextField(blank=True)
    plazo_correccion_limite = models.DateTimeField(blank=True, null=True)
    fecha_cita = models.DateTimeField(blank=True, null=True)
    numero_ficha = models.PositiveIntegerField(blank=True, null=True)
    reenvios = models.PositiveIntegerField(default=0)
    trabajador_asignado = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="solicitudes_asignadas",
        on_delete=models.SET_NULL,
        blank=True,
        null=True
    )
    area_asignada = models.ForeignKey(
        Area,
        related_name="solicitudes_asignadas",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    documentos_snapshot = models.JSONField(default=list, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["estado", "fecha_envio"]),
            models.Index(fields=["fecha_cita"]),
        ]

    def __str__(self):
        return f"Revision {self.inscripcion_id} - {self.get_estado_display()}"


class EventoAuditoria(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="eventos_auditoria",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    evento = models.CharField(max_length=80)
    descripcion = models.CharField(max_length=255)
    ip = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True)
    datos = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["evento", "creado_en"]),
            models.Index(fields=["usuario", "creado_en"]),
        ]
        verbose_name = "Evento de auditoria"
        verbose_name_plural = "Eventos de auditoria"

    def __str__(self):
        return f"{self.evento} - {self.creado_en:%Y-%m-%d %H:%M}"


class NotificacionUsuario(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="notificaciones_usuario",
        on_delete=models.CASCADE
    )
    titulo = models.CharField(max_length=120)
    mensaje = models.TextField()
    leida = models.BooleanField(default=False)
    fecha_creacion = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-fecha_creacion"]

    def __str__(self):
        return f"{self.usuario.username}: {self.titulo}"


class IntentoLoginTrabajador(models.Model):
    username = models.CharField(max_length=150)
    ip = models.GenericIPAddressField(blank=True, null=True)
    intentos_fallidos = models.PositiveSmallIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(blank=True, null=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["username", "ip"], name="uniq_intento_login_trabajador")
        ]

    def __str__(self):
        return f"{self.username} ({self.ip})"


class IntentoLoginUsuario(models.Model):
    username = models.CharField(max_length=150)
    ip = models.GenericIPAddressField(blank=True, null=True)
    intentos_fallidos = models.PositiveSmallIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(blank=True, null=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["username", "ip"], name="uniq_intento_login_usuario")
        ]

    def __str__(self):
        return f"{self.username} ({self.ip})"


class PasswordResetCode(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="reset_codes",
        on_delete=models.CASCADE,
    )
    codigo = models.CharField(max_length=12, blank=True, default="")
    codigo_hash = models.CharField(max_length=128, blank=True, default="")
    creado_en = models.DateTimeField(default=timezone.now)
    usado = models.BooleanField(default=False)
    intentos_fallidos = models.PositiveSmallIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["usuario", "creado_en"]),
            models.Index(fields=["usado"]),
        ]

    def __str__(self):
        return f"Reset {self.usuario_id} ({'usado' if self.usado else 'activo'})"

    def codigo_coincide(self, codigo):
        if self.codigo_hash:
            return check_password(codigo, self.codigo_hash)
        return self.codigo == codigo


class PasswordResetAttempt(models.Model):
    email = models.EmailField()
    ip = models.GenericIPAddressField(blank=True, null=True)
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["email", "creado_en"]),
        ]

    def __str__(self):
        return f"{self.email} ({self.creado_en:%Y-%m-%d %H:%M})"


class TrabajadorPerfil(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="trabajador_perfil",
        on_delete=models.CASCADE
    )
    nombre_completo = models.CharField(max_length=255)
    area = models.ForeignKey(
        Area,
        related_name="trabajadores",
        on_delete=models.PROTECT,
    )
    fecha_registro = models.DateField(auto_now_add=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Perfil trabajador"
        verbose_name_plural = "Perfiles trabajadores"

    def __str__(self):
        return f"{self.nombre_completo} - {self.area}"


def _usuarios_finales_ids():
    User = get_user_model()
    return list(
        User.objects.filter(
            is_active=True,
            is_superuser=False,
            trabajador_perfil__isnull=True,
        ).values_list("id", flat=True)
    )


def _crear_notificaciones_masivas(titulo, mensaje):
    usuarios_ids = _usuarios_finales_ids()
    if not usuarios_ids:
        return
    lotes = []
    for usuario_id in usuarios_ids:
        lotes.append(
            NotificacionUsuario(
                usuario_id=usuario_id,
                titulo=titulo,
                mensaje=mensaje,
            )
        )
    NotificacionUsuario.objects.bulk_create(lotes, batch_size=1000)


@receiver(pre_save, sender=DocumentoCatalogo)
def guardar_estado_anterior_documento_catalogo(sender, instance, **kwargs):
    instance._estado_activo_anterior = None
    if not instance.pk:
        return
    try:
        anterior = DocumentoCatalogo.objects.only("activo").get(pk=instance.pk)
        instance._estado_activo_anterior = anterior.activo
    except DocumentoCatalogo.DoesNotExist:
        instance._estado_activo_anterior = None


@receiver(post_save, sender=DocumentoCatalogo)
def notificar_cambios_documento_catalogo(sender, instance, created, **kwargs):
    if created and instance.activo:
        _crear_notificaciones_masivas(
            "Nuevo documento requerido",
            f"Se agrego el documento '{instance.nombre}'. Ya aparece en tu panel para cargarlo.",
        )
        return

    activo_anterior = getattr(instance, "_estado_activo_anterior", None)
    if activo_anterior is True and not instance.activo:
        _crear_notificaciones_masivas(
            "Documento removido",
            f"El documento '{instance.nombre}' dejo de ser requerido y se retiro de tu panel.",
        )
    if activo_anterior is False and instance.activo:
        _crear_notificaciones_masivas(
            "Documento habilitado",
            f"El documento '{instance.nombre}' fue habilitado y ya aparece en tu panel.",
        )


@receiver(post_delete, sender=Convocatoria)
def eliminar_imagen_convocatoria(sender, instance, **kwargs):
    if instance.imagen and instance.imagen.storage.exists(instance.imagen.name):
        instance.imagen.delete(save=False)


@receiver(pre_save, sender=Convocatoria)
def reemplazo_imagen_convocatoria(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        anterior = Convocatoria.objects.get(pk=instance.pk)
    except Convocatoria.DoesNotExist:
        return
    if anterior.imagen and anterior.imagen != instance.imagen:
        if anterior.imagen.storage.exists(anterior.imagen.name):
            anterior.imagen.delete(save=False)


@receiver(post_delete, sender=DocumentoCatalogo)
def notificar_eliminacion_documento_catalogo(sender, instance, **kwargs):
    if not instance.activo:
        return
    _crear_notificaciones_masivas(
        "Documento eliminado",
        f"El documento '{instance.nombre}' fue eliminado del catalogo y se retiro de tu panel.",
    )



