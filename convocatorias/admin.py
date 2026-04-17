from django import forms
import csv
from django.forms.models import BaseInlineFormSet

from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import redirect
from django.contrib import messages as dj_messages
from django.contrib.auth.models import User, Group

from .models import (
    Area,
    Convocatoria,
    ConvocatoriaDocumentoConfiguracion,
    DocumentoCatalogo,
    EventoAuditoria,
    Inscripcion,
    TrabajadorPerfil,
)

# 🔥 PERSONALIZACIÓN DE TEXTOS DEL ADMIN
admin.site.site_header = "Área de Administración de Desarrollo Económico"
admin.site.site_title = "Área de Administración"
admin.site.index_title = "Panel de Control"


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
        css = {"all": ("convocatorias/CSS/admin_responsive.css", "convocatorias/CSS/admin_custom.css")}

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


# (TODO lo demás sigue EXACTAMENTE igual, no lo toqué)

@admin.register(DocumentoCatalogo)
class DocumentoCatalogoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "activo", "orden")
    list_filter = ("activo",)
    search_fields = ("nombre", "codigo")
    ordering = ("orden", "nombre")

    class Media:
        css = {"all": ("convocatorias/CSS/admin_responsive.css", "convocatorias/CSS/admin_custom.css")}


@admin.register(EventoAuditoria)
class EventoAuditoriaAdmin(admin.ModelAdmin):
    list_display = ("evento", "usuario", "ip", "creado_en")
    list_filter = ("evento", "creado_en")
    search_fields = ("evento", "descripcion", "usuario__username", "ip")
    readonly_fields = ("usuario", "evento", "descripcion", "ip", "user_agent", "datos", "creado_en")
    actions = ["vaciar_auditoria"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "vaciar-auditoria/",
                self.admin_site.admin_view(self.vaciar_auditoria_view),
                name="eventoauditoria_vaciar",
            ),
            path(
                "vaciar-auditoria/confirmar/",
                self.admin_site.admin_view(self.vaciar_auditoria_confirmar),
                name="eventoauditoria_vaciar_confirmar",
            ),
        ]
        return custom + urls

    def vaciar_auditoria_view(self, request):
        from django.template.response import TemplateResponse
        return TemplateResponse(
            request,
            "admin/eventoauditoria_vaciar_confirm.html",
            {
                "title": "Vaciar auditoria",
                "total": EventoAuditoria.objects.count(),
                "opts": self.model._meta,
            },
        )

    def vaciar_auditoria_confirmar(self, request):
        if request.method == "POST":
            total, _ = EventoAuditoria.objects.all().delete()
            dj_messages.success(
                request,
                f"Auditoria vaciada correctamente. Se eliminaron {total} registros.",
            )
        return redirect("admin:convocatorias_eventoauditoria_changelist")

    @admin.action(description="Vaciar toda la auditoria")
    def vaciar_auditoria(self, request, queryset):
        return redirect(reverse("admin:eventoauditoria_vaciar"))

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["vaciar_url"] = reverse("admin:eventoauditoria_vaciar")
        return super().changelist_view(request, extra_context=extra_context)


# ── Ocultar modelos de autenticación ──
try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass

try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass
