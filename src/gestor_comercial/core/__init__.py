"""Infraestrutura transversal, abaixo de todas as outras camadas.

`core/` não conhece `domain/`, `repository/`, `services/` nem `ui/` — e é o
que permite instalar a blindagem no primeiro instante do boot, antes de a
primeira tabela ou o primeiro widget existirem. Só stdlib entra aqui.
"""
