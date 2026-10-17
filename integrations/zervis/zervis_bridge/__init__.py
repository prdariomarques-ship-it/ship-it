"""Ponte Dario OS → Zérvis (ADR-0003, docs/integrations/zervis.md).

Processo separado do backend: lê o Dario OS só por HTTP (token com escopo
`darioos:read`) e pelo canal Redis de eventos, e expõe o resultado ao Zérvis
como servidor MCP somente-leitura. Nada aqui importa código do backend nem do
Zérvis (AGPL-3.0): a fronteira é rede.
"""
