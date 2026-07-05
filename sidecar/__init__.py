"""
Sidecar HTTP local do Helper Financeiro (ADR-0009).

Camada de transporte entre a GUI web (Electron/React, `gui_web/`) e o núcleo
determinístico do `core`. NÃO contém lógica financeira — só traduz JSON para
os objetos do `core` e de volta (REQ-NF-005). Segurança: bind em `127.0.0.1`,
porta efêmera e token de sessão (REQ-SEC-004).
"""
