import os

# ===============================
# CONFIGURAÇÕES
# ===============================
PASTA_RAIZ = os.getcwd()
ARQUIVO_SAIDA = "estrutura_projeto.txt"

IGNORAR_PASTAS = {
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    "venv",
    "env",
    "node_modules"
}

IGNORAR_ARQUIVOS = {
    ".DS_Store"
}

# ===============================
# FUNÇÃO PRINCIPAL
# ===============================
def gerar_estrutura(pasta, nivel=0, arquivo_saida=None):
    try:
        itens = sorted(os.listdir(pasta))
    except PermissionError:
        return

    for item in itens:
        if item in IGNORAR_ARQUIVOS:
            continue

        caminho = os.path.join(pasta, item)
        indentacao = "│   " * nivel + "├── "

        if os.path.isdir(caminho):
            if item in IGNORAR_PASTAS:
                continue

            arquivo_saida.write(f"{indentacao}{item}/\n")
            gerar_estrutura(caminho, nivel + 1, arquivo_saida)
        else:
            arquivo_saida.write(f"{indentacao}{item}\n")

# ===============================
# EXECUÇÃO
# ===============================
with open(ARQUIVO_SAIDA, "w", encoding="utf-8") as f:
    nome_projeto = os.path.basename(PASTA_RAIZ)
    f.write(f"{nome_projeto}/\n")
    gerar_estrutura(PASTA_RAIZ, 0, f)

print(f"✔ Estrutura do projeto gerada em: {ARQUIVO_SAIDA}")
