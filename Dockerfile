# Usa uma imagem oficial do Python como base
FROM python:3.11-slim

# Define o diretório de trabalho dentro do contentor
WORKDIR /app

# Instala dependências do sistema necessárias, se houver (por exemplo, para asyncpg, embora geralmente não seja necessário para esta versão)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libpq-dev \
#     && rm -rf /var/lib/apt/lists/*

# Copia o ficheiro de requisitos e instala as dependências
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copia o resto do código da aplicação
COPY . .

# Expõe a porta que o Uvicorn vai usar
EXPOSE 8000

# Comando para iniciar o servidor Uvicorn quando o contentor for iniciado
# Usamos gunicorn ou uvicorn, mas o Uvicorn é o mais simples para desenvolvimento.
# O '--host 0.0.0.0' é crucial para que o contentor seja acessível a partir do exterior.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
