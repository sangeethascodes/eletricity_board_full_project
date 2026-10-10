from django.db import migrations


def rename_district_column(apps, schema_editor):
    connection = schema_editor.connection
    table_name = apps.get_model('app', 'Applicant')._meta.db_table
    columns = {
        column.name
        for column in connection.introspection.get_table_description(
            connection.cursor(), table_name
        )
    }

    if 'Distric' in columns and 'District' not in columns:
        schema_editor.execute(
            f'ALTER TABLE "{table_name}" RENAME COLUMN "Distric" TO "District"'
        )


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(rename_district_column, migrations.RunPython.noop),
    ]