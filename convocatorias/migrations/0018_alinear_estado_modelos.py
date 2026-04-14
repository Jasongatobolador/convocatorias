from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("convocatorias", "0017_eventoauditoria"),
    ]

    operations = [
        migrations.RenameIndex(
            model_name="eventoauditoria",
            new_name="convocatori_evento_be3280_idx",
            old_name="convocatori_evento_d9c8f6_idx",
        ),
        migrations.RenameIndex(
            model_name="eventoauditoria",
            new_name="convocatori_usuario_cdba28_idx",
            old_name="convocatori_usuario_7dc28f_idx",
        ),
        migrations.RenameIndex(
            model_name="passwordresetattempt",
            new_name="convocatori_email_f8706d_idx",
            old_name="convocatori_email_2502d8_idx",
        ),
        migrations.RenameIndex(
            model_name="passwordresetcode",
            new_name="convocatori_usuario_0319de_idx",
            old_name="convocatori_usuario_4a7b36_idx",
        ),
        migrations.RenameIndex(
            model_name="passwordresetcode",
            new_name="convocatori_usado_3e4683_idx",
            old_name="convocatori_usado_1a21f0_idx",
        ),
        migrations.AlterField(
            model_name="area",
            name="id",
            field=models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
        ),
        migrations.AlterField(
            model_name="trabajadorperfil",
            name="area",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="trabajadores",
                to="convocatorias.area",
            ),
        ),
    ]
