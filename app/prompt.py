from __future__ import annotations

from typing import Dict, Any


SYSTEM_PROMPT = """\
Você é um classificador fiscal para IBS/CBS (LC 214/2025).
Responda SOMENTE em JSON válido, sem markdown.
Não invente regras: se faltar informação, retorne "pendencias".
Explique "fundamento" como lista de objetos {regra, motivo, fonte}.
"""


def build_user_prompt(ctx: Dict[str, Any]) -> str:
    """
    ctx contém:
      - regime_fiscal_emitente, cfop, uf_emitente, uf_destinatario, cst_icms, ncm, data_emissao
      - dados de categoria do ncm_master e anexos (se existirem)
      - transições/aliquotas base (se existirem)
    """
    return (
        "Classifique a operação e determine:\n"
        "1) cclastrib (codigo, descricao)\n"
        "2) cst IBS/CBS e cClassTrib\n"
        "3) aliquotas IBS e CBS (considerando transição por ano e reduções por categoria)\n"
        "4) fundamento detalhado\n\n"
        f"Contexto:\n{ctx}\n"
    )
