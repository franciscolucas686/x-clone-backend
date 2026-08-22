"""Views transversais, sem dono de domínio."""

from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def healthz(request):
    """Endpoint de keep-alive.

    Existe separado de `/api/docs/` de propósito. A documentação também não toca o
    banco, mas introspecciona a API inteira a cada chamada — cada requisição regenera o
    schema OpenAPI do zero. Pingado a cada 5 minutos, 24h por dia, isso é trabalho
    supérfluo. Este endpoint só confirma que o processo está vivo: sem banco, sem
    serializer, sem dependência de nada que possa quebrar por outro motivo e derrubar
    o keep-alive junto.
    """
    return JsonResponse({"status": "ok"})
