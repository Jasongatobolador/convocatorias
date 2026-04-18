from django.urls import path
from . import views

urlpatterns = [
    path('c', views.home_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('admin-acceso/', views.admin_logout_redirect_view, name='admin_logout_redirect'),  # ← cierra sesión y va al login admin
    path('recuperar-contrasena/', views.password_reset_view, name='password_reset'),
    path('trabajador/login/', views.login_trabajador_view, name='login_trabajador'),
    path('registro/', views.registro_view, name='registro'),
    path('terminos-y-condiciones/', views.terminos_condiciones_view, name='terminos_condiciones'),
    path('logout/', views.logout_view, name='logout'),
    path('convocatorias/', views.lista_convocatorias, name='lista_convocatorias'),
    path('detalle/<int:id>/', views.detalle_convocatoria, name='detalle_convocatoria'),
    path('detalle/<int:id>/unirse/', views.unirse_convocatoria_view, name='unirse_convocatoria'),
    path('trabajador/dashboard/', views.dashboard_trabajador_view, name='dashboard_trabajador'),
    path('trabajador/solicitud/<int:solicitud_id>/', views.revisar_solicitud_trabajador_view, name='revisar_solicitud_trabajador'),
    path('usuario/', views.zona_usuario_view, name='zona_usuario'),
    path('usuario/documento/<int:documento_id>/ver/', views.ver_documento_usuario_view, name='ver_documento_usuario'),
    path('usuario/documentos/', views.gestion_documentos_view, name='gestion_documentos'),
    path(
        'trabajador/solicitud/<int:solicitud_id>/documento/<int:indice>/ver/',
        views.ver_documento_snapshot_trabajador_view,
        name='ver_documento_snapshot_trabajador',
    ),
    path('verificacion-token/', views.verificacion_token_view, name='verificacion_token'),
    path('validacion-convocatoria/', views.validacion_convocatoria_view, name='validacion_convocatoria'),
    path('documentos-faltantes/', views.documentos_faltantes_view, name='documentos_faltantes'),
    path('documento-extra/', views.documento_extra_view, name='documento_extra'),
    path('registro-exitoso/', views.registro_exitoso_view, name='registro_exitoso'),
]
