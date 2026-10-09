from django.db import connection


def reset_sequence(table_name):
    """
    Reinicia el auto-increment de una tabla.
    Compatible con SQLite, PostgreSQL y MySQL.
    """
    vendor = connection.vendor

    with connection.cursor() as cursor:
        if vendor == 'sqlite':
            cursor.execute(
                f"DELETE FROM sqlite_sequence WHERE name='{table_name}'"
            )
        elif vendor == 'postgresql':
            # PostgreSQL usa secuencias con el patrón tablename_columnname_seq
            cursor.execute(
                f"ALTER SEQUENCE {table_name}_id_seq RESTART WITH 1"
            )
        elif vendor == 'mysql':
            cursor.execute(
                f"ALTER TABLE {table_name} AUTO_INCREMENT = 1"
            )
        else:
            raise ValueError(f"Motor de base de datos no soportado: {vendor}")