import os
import sys


def main():
    # Default de desenvolvimento. Produção define DJANGO_SETTINGS_MODULE
    # explicitamente (ver Dockerfile.prod). O default anterior era
    # "backend.settings.production", o que fazia o `manage.py migrate` do README
    # estourar em ImproperlyConfigured num clone novo e o CI rodar os testes sob
    # settings de produção sem que nada indicasse isso.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.development")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
