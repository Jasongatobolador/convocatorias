from datetime import timedelta
import re

from django.core import mail
from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import SubidaDocumentoForm
from .models import (
    Area,
    Convocatoria,
    ConvocatoriaDocumentoConfiguracion,
    DocumentoCatalogo,
    DocumentoUsuario,
    EventoAuditoria,
    Inscripcion,
    IntentoLoginUsuario,
    NotificacionUsuario,
    PasswordResetCode,
    SolicitudRevision,
    TrabajadorPerfil,
)


class RegistroTerminosTests(TestCase):
    def test_sin_aceptar_terminos_redirige_a_login(self):
        url = reverse("registro")
        response = self.client.post(
            url,
            {
                "email": "nuevo@example.com",
                "password1": "PruebaSegura123!",
                "password2": "PruebaSegura123!",
            },
        )
        self.assertRedirects(response, reverse("login"))
        self.assertFalse(User.objects.filter(username="nuevo@example.com").exists())


class SeguridadLoginTrabajadorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="worker@example.com",
            email="worker@example.com",
            password="Segura123!",
            is_active=True,
        )
        area = Area.objects.create(nombre="Area 1", descripcion="Area generica", activa=True)
        TrabajadorPerfil.objects.create(
            usuario=self.user,
            nombre_completo="Worker Uno",
            area=area,
            activo=True,
        )

    @override_settings(WORKER_MAX_LOGIN_FAILED=1, WORKER_LOGIN_BLOCK_MINUTES=5)
    def test_bloquea_login_tras_intento_fallido(self):
        url = reverse("login_trabajador")
        self.client.post(url, {"email": "worker@example.com", "password": "mala"})

        response = self.client.post(url, {"email": "worker@example.com", "password": "Segura123!"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cuenta temporalmente bloqueada")


class SeguridadSubidaDocumentoTests(TestCase):
    def setUp(self):
        self.doc, _ = DocumentoCatalogo.objects.get_or_create(
            codigo="curp",
            defaults={
                "nombre": "CURP",
                "activo": True,
            },
        )

    def test_rechaza_pdf_sin_firma_valida(self):
        fake_pdf = SimpleUploadedFile("archivo.pdf", b"NO-ES-PDF", content_type="application/pdf")
        form = SubidaDocumentoForm(
            data={"tipo": self.doc.codigo},
            files={"archivo": fake_pdf},
            documentos_disponibles=[self.doc],
        )
        self.assertFalse(form.is_valid())
        self.assertIn("archivo", form.errors)

    def test_rechaza_imagen_invalida_con_extension_png(self):
        fake_png = SimpleUploadedFile("imagen.png", b"contenido-no-imagen", content_type="image/png")
        form = SubidaDocumentoForm(
            data={"tipo": self.doc.codigo},
            files={"archivo": fake_png},
            documentos_disponibles=[self.doc],
        )
        self.assertFalse(form.is_valid())
        self.assertIn("archivo", form.errors)

    def test_rechaza_extension_peligrosa(self):
        fake_exe = SimpleUploadedFile("malware.exe", b"MZ-binario-falso", content_type="application/octet-stream")
        form = SubidaDocumentoForm(
            data={"tipo": self.doc.codigo},
            files={"archivo": fake_exe},
            documentos_disponibles=[self.doc],
        )
        self.assertFalse(form.is_valid())
        self.assertIn("archivo", form.errors)


class SeguridadPermisosTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(nombre="Area Seguridad", descripcion="Pruebas", activa=True)
        self.convocatoria = Convocatoria.objects.create(
            titulo="Convocatoria de prueba",
            area=self.area,
            descripcion="Descripcion",
            dependencia="Dependencia",
            objetivo="Objetivo",
            dirigido_a="Dirigido",
            requisitos="Requisitos",
            beneficios="Beneficios",
            fecha_inicio=timezone.localdate() - timedelta(days=1),
            fecha_fin=timezone.localdate() + timedelta(days=5),
            fecha_inicio_recepcion=timezone.localdate(),
            fecha_fin_recepcion=timezone.localdate() + timedelta(days=2),
            lugar_recepcion="Modulo 1",
            horario="10:00 a 14:00",
            forma_entrega="Presencial",
            contacto="correo@example.com",
            personas_maximas_por_dia=10,
        )
        self.usuario_1 = User.objects.create_user(
            username="usuario1@example.com",
            email="usuario1@example.com",
            password="Segura123!",
        )
        self.usuario_2 = User.objects.create_user(
            username="usuario2@example.com",
            email="usuario2@example.com",
            password="Segura123!",
        )
        self.worker_1 = User.objects.create_user(
            username="worker1@example.com",
            email="worker1@example.com",
            password="Segura123!",
        )
        self.worker_2 = User.objects.create_user(
            username="worker2@example.com",
            email="worker2@example.com",
            password="Segura123!",
        )
        TrabajadorPerfil.objects.create(
            usuario=self.worker_1,
            nombre_completo="Trabajador Uno",
            area=self.area,
            activo=True,
        )
        TrabajadorPerfil.objects.create(
            usuario=self.worker_2,
            nombre_completo="Trabajador Dos",
            area=self.area,
            activo=True,
        )

    def test_usuario_no_puede_ver_documento_de_otro(self):
        documento = DocumentoUsuario.objects.create(
            usuario=self.usuario_1,
            tipo="curp",
            archivo_nombre="doc.pdf",
            archivo_mime="application/pdf",
            archivo_tamano=8,
            archivo_binario=b"%PDF-1.4",
        )
        self.client.force_login(self.usuario_2)

        response = self.client.get(reverse("ver_documento_usuario", args=[documento.id]))

        self.assertEqual(response.status_code, 404)

    def test_trabajador_no_asignado_no_puede_revisar_solicitud(self):
        inscripcion = Inscripcion.objects.create(
            convocatoria=self.convocatoria,
            usuario=self.usuario_1,
            estado=Inscripcion.Estado.ACTIVA,
        )
        solicitud = SolicitudRevision.objects.create(
            inscripcion=inscripcion,
            trabajador_asignado=self.worker_1,
            area_asignada=self.area,
        )
        self.client.force_login(self.worker_2)

        response = self.client.get(reverse("revisar_solicitud_trabajador", args=[solicitud.id]))

        self.assertRedirects(response, reverse("dashboard_trabajador"))
        self.assertTrue(
            EventoAuditoria.objects.filter(
                evento="acceso_denegado_revision",
                datos__solicitud_id=solicitud.id,
            ).exists()
        )

    def test_usuario_final_no_puede_entrar_dashboard_trabajador(self):
        self.client.force_login(self.usuario_1)

        response = self.client.get(reverse("dashboard_trabajador"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login_trabajador"))
        self.assertTrue(
            EventoAuditoria.objects.filter(
                evento="acceso_denegado_panel_trabajador",
                datos__path=reverse("dashboard_trabajador"),
            ).exists()
        )

    def test_detalle_convocatoria_muestra_condiciones_documentales(self):
        documento, _ = DocumentoCatalogo.objects.get_or_create(
            codigo="ine_prueba",
            defaults={
                "nombre": "Identificacion especial",
                "descripcion": "Documento de prueba",
                "activo": True,
                "orden": 10,
            },
        )
        ConvocatoriaDocumentoConfiguracion.objects.create(
            convocatoria=self.convocatoria,
            documento=documento,
            copias=2,
            requiere_original=True,
        )
        self.client.force_login(self.usuario_1)

        response = self.client.get(reverse("detalle_convocatoria", args=[self.convocatoria.id]))

        self.assertContains(response, "Entregar 2 copias, presentar original")


class FlujoAplicacionTests(TestCase):
    def setUp(self):
        self.area = Area.objects.create(nombre="Area Flujo", descripcion="Pruebas de flujo", activa=True)
        self.convocatoria = Convocatoria.objects.create(
            titulo="Convocatoria integral",
            area=self.area,
            descripcion="Descripcion",
            dependencia="Dependencia",
            objetivo="Objetivo",
            dirigido_a="Dirigido",
            requisitos="Requisitos",
            beneficios="Beneficios",
            fecha_inicio=timezone.localdate() - timedelta(days=1),
            fecha_fin=timezone.localdate() + timedelta(days=5),
            fecha_inicio_recepcion=timezone.localdate(),
            fecha_fin_recepcion=timezone.localdate() + timedelta(days=2),
            lugar_recepcion="Modulo central",
            horario="10:00 a 14:00",
            forma_entrega="Presencial",
            contacto="correo@example.com",
            personas_maximas_por_dia=5,
        )

        self.doc_curp, _ = DocumentoCatalogo.objects.get_or_create(
            codigo="curp",
            defaults={
                "nombre": "CURP",
                "activo": True,
                "orden": 1,
            },
        )
        self.doc_ine, _ = DocumentoCatalogo.objects.get_or_create(
            codigo="identificacion_oficial",
            defaults={
                "nombre": "Identificacion oficial",
                "activo": True,
                "orden": 2,
            },
        )
        self.doc_dom, _ = DocumentoCatalogo.objects.get_or_create(
            codigo="comprobante_domicilio",
            defaults={
                "nombre": "Comprobante de domicilio",
                "activo": True,
                "orden": 3,
            },
        )
        self.convocatoria.documentos_requeridos.set([self.doc_curp, self.doc_ine, self.doc_dom])

        self.usuario = User.objects.create_user(
            username="usuario@prueba.com",
            email="usuario@prueba.com",
            password="Segura123!",
        )
        self.usuario_2 = User.objects.create_user(
            username="usuario2@prueba.com",
            email="usuario2@prueba.com",
            password="Segura123!",
        )
        self.worker = User.objects.create_user(
            username="worker@prueba.com",
            email="worker@prueba.com",
            password="Segura123!",
        )
        TrabajadorPerfil.objects.create(
            usuario=self.worker,
            nombre_completo="Worker Prueba",
            area=self.area,
            activo=True,
        )

    def _cargar_documentos_usuario(self, usuario):
        DocumentoUsuario.objects.update_or_create(
            usuario=usuario,
            tipo="curp",
            defaults={
                "archivo_nombre": "curp.pdf",
                "archivo_mime": "application/pdf",
                "archivo_tamano": 8,
                "archivo_binario": b"%PDF-1.4",
                "estado": DocumentoUsuario.Estado.ACEPTADO,
            },
        )
        DocumentoUsuario.objects.update_or_create(
            usuario=usuario,
            tipo="identificacion_oficial",
            defaults={
                "archivo_nombre": "ine.pdf",
                "archivo_mime": "application/pdf",
                "archivo_tamano": 8,
                "archivo_binario": b"%PDF-1.4",
                "estado": DocumentoUsuario.Estado.ACEPTADO,
            },
        )
        DocumentoUsuario.objects.update_or_create(
            usuario=usuario,
            tipo="comprobante_domicilio",
            defaults={
                "archivo_nombre": "domicilio.pdf",
                "archivo_mime": "application/pdf",
                "archivo_tamano": 8,
                "archivo_binario": b"%PDF-1.4",
                "estado": DocumentoUsuario.Estado.ACEPTADO,
            },
        )

    def test_registro_crea_usuario_y_redirige_a_convocatorias(self):
        response = self.client.post(
            reverse("registro"),
            {
                "email": "nuevo@prueba.com",
                "password1": "PruebaSegura123!",
                "password2": "PruebaSegura123!",
                "acepta_terminos": "on",
            },
        )
        self.assertRedirects(response, reverse("lista_convocatorias"))
        self.assertTrue(User.objects.filter(username="nuevo@prueba.com").exists())

    def test_login_usuario_correcto_redirige_a_lista(self):
        response = self.client.post(
            reverse("login"),
            {"email": self.usuario.username, "password": "Segura123!"},
        )
        self.assertRedirects(response, reverse("lista_convocatorias"))

    def test_login_usuario_incorrecto_muestra_error(self):
        response = self.client.post(
            reverse("login"),
            {"email": self.usuario.username, "password": "incorrecta"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Credenciales incorrectas")

    def test_login_trabajador_correcto_redirige_a_dashboard(self):
        response = self.client.post(
            reverse("login_trabajador"),
            {"email": self.worker.username, "password": "Segura123!"},
        )
        self.assertRedirects(response, reverse("dashboard_trabajador"))

    def test_login_trabajador_incorrecto_muestra_error(self):
        response = self.client.post(
            reverse("login_trabajador"),
            {"email": self.worker.username, "password": "incorrecta"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Credenciales incorrectas")

    def test_login_ignora_x_forwarded_for_no_confiable(self):
        self.client.post(
            reverse("login"),
            {"email": self.usuario.username, "password": "incorrecta"},
            REMOTE_ADDR="203.0.113.10",
            HTTP_X_FORWARDED_FOR="8.8.8.8",
        )
        self.assertTrue(
            IntentoLoginUsuario.objects.filter(
                username=self.usuario.username,
                ip="203.0.113.10",
            ).exists()
        )
        self.assertFalse(
            IntentoLoginUsuario.objects.filter(
                username=self.usuario.username,
                ip="8.8.8.8",
            ).exists()
        )

    def test_entrar_a_login_con_sesion_activa_la_cierra(self):
        self.client.force_login(self.usuario)
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse("_auth_user_id" in self.client.session)
        self.assertContains(response, "Iniciar sesion")

    def test_entrar_a_login_trabajador_con_sesion_activa_la_cierra(self):
        self.client.force_login(self.worker)
        response = self.client.get(reverse("login_trabajador"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse("_auth_user_id" in self.client.session)
        self.assertContains(response, "Iniciar sesion")

    def test_unirse_convocatoria_requiere_post(self):
        self.client.force_login(self.usuario)
        response = self.client.get(reverse("unirse_convocatoria", args=[self.convocatoria.id]))
        self.assertEqual(response.status_code, 405)

    def test_subida_documento_valido_es_aceptado(self):
        pdf = SimpleUploadedFile("curp.pdf", b"%PDF-1.4\ncontenido", content_type="application/pdf")
        form = SubidaDocumentoForm(
            data={"tipo": self.doc_curp.codigo},
            files={"archivo": pdf},
            documentos_disponibles=[self.doc_curp],
        )
        self.assertTrue(form.is_valid())

    def test_inscripcion_crea_solicitud_y_notificacion(self):
        self._cargar_documentos_usuario(self.usuario)
        self.client.force_login(self.usuario)
        response = self.client.post(reverse("unirse_convocatoria", args=[self.convocatoria.id]))
        self.assertRedirects(response, reverse("detalle_convocatoria", args=[self.convocatoria.id]))
        self.assertTrue(
            Inscripcion.objects.filter(
                convocatoria=self.convocatoria,
                usuario=self.usuario,
                estado=Inscripcion.Estado.ACTIVA,
            ).exists()
        )
        self.assertTrue(
            SolicitudRevision.objects.filter(
                inscripcion__convocatoria=self.convocatoria,
                inscripcion__usuario=self.usuario,
                estado=SolicitudRevision.Estado.PENDIENTE,
            ).exists()
        )
        self.assertTrue(
            NotificacionUsuario.objects.filter(
                usuario=self.usuario,
                titulo="Solicitud enviada",
            ).exists()
        )

    def test_cupo_lleno_bloquea_segundo_usuario(self):
        self.convocatoria.fecha_fin_recepcion = self.convocatoria.fecha_inicio_recepcion
        self.convocatoria.personas_maximas_por_dia = 1
        self.convocatoria.save()
        self._cargar_documentos_usuario(self.usuario)
        self._cargar_documentos_usuario(self.usuario_2)
        Inscripcion.objects.create(
            convocatoria=self.convocatoria,
            usuario=self.usuario,
            estado=Inscripcion.Estado.ACTIVA,
        )
        self.client.force_login(self.usuario_2)
        response = self.client.post(reverse("unirse_convocatoria", args=[self.convocatoria.id]))
        self.assertRedirects(response, reverse("detalle_convocatoria", args=[self.convocatoria.id]))
        self.assertEqual(
            Inscripcion.objects.filter(convocatoria=self.convocatoria, estado=Inscripcion.Estado.ACTIVA).count(),
            1,
        )

    def test_rechazo_con_reenvio_y_correccion(self):
        self._cargar_documentos_usuario(self.usuario)
        inscripcion = Inscripcion.objects.create(
            convocatoria=self.convocatoria,
            usuario=self.usuario,
            estado=Inscripcion.Estado.ACTIVA,
        )
        solicitud = SolicitudRevision.objects.create(
            inscripcion=inscripcion,
            trabajador_asignado=self.worker,
            area_asignada=self.area,
        )
        self.client.force_login(self.worker)
        response = self.client.post(
            reverse("revisar_solicitud_trabajador", args=[solicitud.id]),
            {
                "accion": "rechazar",
                "motivo_rechazo": "Documento ilegible",
                "permitir_reenvio": "on",
                "plazo_correccion_dias": "2",
            },
        )
        self.assertRedirects(response, reverse("dashboard_trabajador"))
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, SolicitudRevision.Estado.RECHAZADA)
        self.assertTrue(solicitud.plazo_correccion_limite is not None)

        self.client.force_login(self.usuario)
        response = self.client.post(
            reverse("zona_usuario"),
            {
                "accion": "reenviar_solicitud",
                "solicitud_id": solicitud.id,
            },
        )
        self.assertRedirects(response, reverse("zona_usuario"))
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, SolicitudRevision.Estado.PENDIENTE)
        self.assertEqual(solicitud.reenvios, 1)
        self.assertTrue(
            NotificacionUsuario.objects.filter(usuario=self.usuario, titulo="Solicitud reenviada").exists()
        )

    def test_aceptacion_asigna_cita_y_ficha(self):
        self._cargar_documentos_usuario(self.usuario)
        inscripcion = Inscripcion.objects.create(
            convocatoria=self.convocatoria,
            usuario=self.usuario,
            estado=Inscripcion.Estado.ACTIVA,
        )
        solicitud = SolicitudRevision.objects.create(
            inscripcion=inscripcion,
            trabajador_asignado=self.worker,
            area_asignada=self.area,
        )
        self.client.force_login(self.worker)
        response = self.client.post(
            reverse("revisar_solicitud_trabajador", args=[solicitud.id]),
            {"accion": "aceptar"},
        )
        self.assertRedirects(response, reverse("dashboard_trabajador"))
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, SolicitudRevision.Estado.ACEPTADA)
        self.assertIsNotNone(solicitud.fecha_cita)
        self.assertIsNotNone(solicitud.numero_ficha)
        self.assertTrue(
            NotificacionUsuario.objects.filter(usuario=self.usuario, titulo="Solicitud aceptada").exists()
        )

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_codigo_de_recuperacion_se_guarda_hasheado(self):
        response = self.client.post(
            reverse("password_reset"),
            {"step": "request", "email": self.usuario.username},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

        contenido = mail.outbox[0].body
        coincidencia = re.search(r"Codigo de verificacion: (\d{6})", contenido)
        self.assertIsNotNone(coincidencia)
        codigo = coincidencia.group(1)

        registro = PasswordResetCode.objects.filter(usuario=self.usuario, usado=False).latest("creado_en")
        self.assertEqual(registro.codigo, "")
        self.assertTrue(registro.codigo_hash)
        self.assertTrue(registro.codigo_coincide(codigo))
        self.assertFalse(check_password("000000", registro.codigo_hash))

    def test_respuesta_incluye_cabeceras_de_seguridad(self):
        response = self.client.get(reverse("home"))
        self.assertIn("Content-Security-Policy", response)
        self.assertIn("script-src 'self'", response["Content-Security-Policy"])
        self.assertIn("object-src 'none'", response["Content-Security-Policy"])

    def test_zona_usuario_muestra_documentos_cargados(self):
        self._cargar_documentos_usuario(self.usuario)
        self.client.force_login(self.usuario)
        response = self.client.get(reverse("zona_usuario"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mis documentos")
