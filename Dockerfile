FROM python:3.11-slim

# Variáveis recomendadas para Docker + Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código da aplicação
COPY app ./app

# Dados fiscais (CSV, anexos, etc.)
COPY data ./data

# Porta do serviço
EXPOSE 8000

# Inicialização
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
