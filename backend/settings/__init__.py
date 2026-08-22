"""Pacote de settings.

Este módulo é deliberadamente vazio. Ele já foi um dispatcher que lia `DJANGO_ENV` e
importava development ou production — um segundo mecanismo de seleção de ambiente,
concorrendo com o `DJANGO_SETTINGS_MODULE` do manage.py e discordando dele: o manage.py
tinha default de produção, este arquivo tinha default de desenvolvimento, e `DJANGO_ENV`
nunca era definida por nenhum Dockerfile, compose ou workflow.

O efeito visível era o CI rodar a suíte de testes sob settings de produção sem que nada
indicasse isso. O ambiente agora é escolhido num lugar só: DJANGO_SETTINGS_MODULE.
"""
