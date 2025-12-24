from bs4 import BeautifulSoup
import csv
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
HTML_FILE = os.path.join(BASE_DIR, "data/lei/lc214_2025.html")
OUT_DIR = os.path.join(BASE_DIR, "data/csv")

os.makedirs(OUT_DIR, exist_ok=True)

# -------------------------------------------------
# Ler HTML com encoding correto
# -------------------------------------------------
with open(HTML_FILE, "r", encoding="latin-1") as f:
    soup = BeautifulSoup(f, "html.parser")

# -------------------------------------------------
# Regex para ANEXO I, II, III, ...
# -------------------------------------------------
ANEXO_REGEX = re.compile(r"ANEXO\s+[IVXLCDM]+", re.IGNORECASE)

# -------------------------------------------------
# Encontrar todos os pontos de anexo
# -------------------------------------------------
anexo_nodes = []

for tag in soup.find_all(True):
    texto = tag.get_text(strip=True)
    if texto and ANEXO_REGEX.match(texto):
        anexo_nodes.append(tag)

print(f"🔎 Anexos encontrados: {len(anexo_nodes)}")

# -------------------------------------------------
# Para cada anexo, coletar tabelas até o próximo
# -------------------------------------------------
for idx, anexo_tag in enumerate(anexo_nodes):
    raw_titulo = anexo_tag.get_text(separator=" ", strip=True).upper()

    # Normalizar espaços e quebras
    titulo = re.sub(r"\s+", " ", raw_titulo).strip()

    # Nome seguro para arquivo
    nome_anexo = titulo.replace(" ", "_")

    tabelas = []
    current = anexo_tag

    while True:
        current = current.find_next()
        if not current:
            break

        # Se achou outro anexo → parar
        texto = current.get_text(strip=True)
        if texto and ANEXO_REGEX.match(texto):
            break

        if current.name == "table":
            tabelas.append(current)

    if not tabelas:
        print(f"⚠ Nenhuma tabela encontrada em {nome_anexo}")
        continue

    csv_path = os.path.join(OUT_DIR, f"{nome_anexo}.csv")

    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile, delimiter=";")
        writer.writerow([
            "anexo",
            "linha",
            "ncm",
            "descricao",
            "aliquota",
            "observacao",
            "vigencia_inicio",
            "vigencia_fim"
        ])

        linha = 1
        for table in tabelas:
            for row in table.find_all("tr"):
                cols = [
                    c.get_text(" ", strip=True)
                    for c in row.find_all(["td", "th"])
                ]

                # Ignorar linhas vazias ou cabeçalho
                if len(cols) < 2 or "NCM" in cols[0].upper():
                    continue

                ncm = cols[0]
                descricao = cols[1]
                aliquota = cols[2] if len(cols) > 2 else ""

                writer.writerow([
                    titulo,
                    linha,
                    ncm,
                    descricao,
                    aliquota,
                    "",
                    "",
                    ""
                ])
                linha += 1

    print(f"✔ Gerado: {csv_path}")
