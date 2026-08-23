"""Normalização de campos de conta que não são só validação.

Separado de `serializers.py` porque `capitalizar_nome` não depende de nada do DRF —
é texto puro — e assim dá para testar sem montar um serializer em volta.
"""

# Preposições/conectivos comuns em nomes brasileiros, que ficam minúsculos quando não
# são a primeira palavra do nome (ex.: "João da Silva", nunca "João Da Silva").
CONECTIVOS_MINUSCULOS = {"de", "da", "do", "das", "dos", "e"}


def capitalizar_nome(nome: str) -> str:
    """Primeira letra maiúscula em cada palavra, exceto conectivos no meio do nome.

    A primeira palavra nunca vira conectivo minúsculo, mesmo que coincida com um —
    "Da Silva", sozinho, começa maiúsculo. Hífen é tratado por partes ("ana-beatriz"
    -> "Ana-Beatriz"). `str.capitalize()` já lida certo com acentuação.
    """
    nome = nome.strip()
    if not nome:
        return nome

    palavras = nome.split()
    resultado = []
    for indice, palavra in enumerate(palavras):
        partes = palavra.split("-")
        formatadas = [
            parte.lower()
            if parte.lower() in CONECTIVOS_MINUSCULOS and indice != 0
            else parte.capitalize()
            for parte in partes
        ]
        resultado.append("-".join(formatadas))
    return " ".join(resultado)
