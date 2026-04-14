from django import forms
import csv
from django.forms.models import BaseInlineFormSet

from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html
from django.urls import path
from django.contrib.auth.models import User

from .models import (
    Area,
    Convocatoria,
    ConvocatoriaDocumentoConfiguracion,
    DocumentoCatalogo,
    EventoAuditoria,
    Inscripcion,
    TrabajadorPerfil,
)


class ConvocatoriaAdminForm(forms.ModelForm):
    class Meta:
        model = Convocatoria
        exclude = (
            "imagen",
            "duracion_cita_minutos",
            "horario",
            "hora_recepcion_inicio",
            "hora_recepcion_fin",
            "documentos_requeridos",
        )


class ConvocatoriaDocumentoConfiguracionInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        total_validos = 0
        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE", False):
                continue
            if form.cleaned_data.get("documento"):
                total_validos += 1
        if total_validos == 0:
            raise forms.ValidationError("Agrega al menos un documento requerido para la convocatoria.")


class ConvocatoriaDocumentoConfiguracionInline(admin.TabularInline):
    model = ConvocatoriaDocumentoConfiguracion
    formset = ConvocatoriaDocumentoConfiguracionInlineFormSet
    extra = 1
    min_num = 1
    fields = ("documento", "copias", "requiere_original")
    verbose_name = "Documento requerido"
    verbose_name_plural = "Documentos requeridos y condiciones de entrega"


@admin.register(Convocatoria)
class ConvocatoriaAdmin(admin.ModelAdmin):
    form = ConvocatoriaAdminForm
    inlines = (ConvocatoriaDocumentoConfiguracionInline,)
    readonly_fields = ("fecha_publicacion", "dias_recepcion", "cupo_maximo")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "titulo",
                    "area",
                    "descripcion",
                    "dependencia",
                    "objetivo",
                    "dirigido_a",
                    "requisitos",
                    "beneficios",
                )
            },
        ),
        (
            "Periodo de convocatoria",
            {
                "fields": ("fecha_inicio", "fecha_fin", "activa", "fecha_publicacion"),
            },
        ),
        (
            "Periodo de recepcion de documentos",
            {
                "fields": (
                    "fecha_inicio_recepcion",
                    "fecha_fin_recepcion",
                    "personas_maximas_por_dia",
                    "dias_recepcion",
                    "cupo_maximo",
                )
            },
        ),
        (
            "Logistica",
            {
                "fields": ("lugar_recepcion", "forma_entrega", "contacto"),
            },
        ),
    )
    list_display = (
        "titulo",
        "area",
        "activa",
        "fecha_publicacion",
        "cupo_maximo",
        "personas_maximas_por_dia",
        "fecha_inicio_recepcion",
        "fecha_fin_recepcion",
        "imprimir",
    )
    list_filter = ("activa", "fecha_publicacion", "area")
    search_fields = ("titulo", "dependencia")

    class Media:
        js = ("convocatorias/js/admin_convocatoria.js",)
        css = {"all": ("convocatorias/CSS/admin_responsive.css",)}

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:convocatoria_id>/exportar-inscritos/",
                self.admin_site.admin_view(self.exportar_inscritos),
                name="convocatorias_convocatoria_exportar_inscritos",
            ),
        ]
        return custom + urls

    @admin.display(description="Imprimir")
    def imprimir(self, obj):
        return format_html(
            '<a class="button" href="{}">Imprimir</a>',
            f"{obj.id}/exportar-inscritos/",
        )

    def exportar_inscritos(self, request, convocatoria_id):
        convocatoria = Convocatoria.objects.get(pk=convocatoria_id)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="inscritos_convocatoria_{convocatoria_id}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(["Nombre completo", "Direccion"])
        inscritos = (
            convocatoria.inscripciones.select_related("usuario")
            .filter(estado=Inscripcion.Estado.ACTIVA)
        )
        for inscripcion in inscritos:
            perfil = getattr(inscripcion.usuario, "perfil_usuario", None)
            if perfil:
                writer.writerow([perfil.nombre_completo, perfil.direccion])
            else:
                writer.writerow(["", ""])
        return response


@admin.register(DocumentoCatalogo)
class DocumentoCatalogoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "activo", "orden")
    list_filter = ("activo",)
    search_fields = ("nombre", "codigo")
    ordering = ("orden", "nombre")

    class Media:
        css = {"all": ("convocatorias/CSS/admin_responsive.css",)}


@admin.register(EventoAuditoria)
class EventoAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("evento", "usuario", "ip", "creado_en")
    list_filter = ("evento", "creado_en")
    search_fields = ("evento", "descripcion", "usuario__username", "ip")
    readonly_fields = ("usuario", "evento", "descripcion", "ip", "user_agent", "datos", "creado_en")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    class Media:
        css = {"all": ("convocatorias/CSS/admin_responsive.css",)}


class TrabajadorPerfilAdminForm(forms.ModelForm):
    email = forms.EmailField(label="Correo")
    password = forms.CharField(label="Contrasena", widget=forms.PasswordInput)

    class Meta:
        model = TrabajadorPerfil
        fields = ("nombre_completo", "area", "activo", "email", "password")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError(
                "Ese correo ya esta registrado. Usa otro correo para el trabajador."
            )
        return email

    def save(self, commit=True):
        email = self.cleaned_data["email"]
        password = self.cleaned_data["password"]
        nombre = self.cleaned_data["nombre_completo"].strip()

        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            is_staff=False,
            is_active=self.cleaned_data.get("activo", True),
        )
        user.first_name = nombre
        user.save(update_fields=["first_name"])

        perfil = super().save(commit=False)
        perfil.usuario = user
        if commit:
            perfil.save()
        return perfil


class TrabajadorPerfilEditForm(forms.ModelForm):
    email = forms.EmailField(label="Correo", required=False, disabled=True)
    password_nueva = forms.CharField(
        label="Nueva contrasena (opcional)",
        widget=forms.PasswordInput,
        required=False,
        help_text="Si se captura, reemplaza la contrasena actual del trabajador.",
    )

    class Meta:
        model = TrabajadorPerfil
        fields = ("nombre_completo", "area", "activo")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.usuario_id:
            self.fields["email"].initial = self.instance.usuario.email


@admin.register(TrabajadorPerfil)
class TrabajadorPerfilAdmin(admin.ModelAdmin):
    list_display = ("nombre_completo", "usuario", "correo", "area", "fecha_registro", "activo")
    list_filter = ("area", "activo", "fecha_registro")
    search_fields = ("nombre_completo", "usuario__username", "usuario__email")
    readonly_fields = ("fecha_registro",)

    class Media:
        css = {"all": ("convocatorias/CSS/admin_responsive.css",)}

    @admin.display(description="Correo")
    def correo(self, obj):
        return obj.usuario.email

    def get_form(self, request, obj=None, **kwargs):
        defaults = kwargs.copy()
        if obj is None:
            defaults["form"] = TrabajadorPerfilAdminForm
        else:
            defaults["form"] = TrabajadorPerfilEditForm
        return super().get_form(request, obj, **defaults)

    def save_model(self, request, obj, form, change):
        if change:
            password_nueva = form.cleaned_data.get("password_nueva")
            if password_nueva:
                obj.usuario.set_password(password_nueva)
            obj.usuario.is_active = obj.activo
            obj.usuario.is_staff = False
            campos = ["is_active", "is_staff"]
            if password_nueva:
                campos.append("password")
            obj.usuario.save(update_fields=campos)
        super().save_model(request, obj, form, change)
@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activa", "fecha_registro")
    list_filter = ("activa", "fecha_registro")
    search_fields = ("nombre",)

    class Media:
        css = {"all": ("convocatorias/CSS/admin_responsive.css",)}
