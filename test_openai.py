from openai import OpenAI
from dotenv import load_dotenv
import os

# Carrega o .env
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise RuntimeError("OPENAI_API_KEY não foi carregada")

client = OpenAI(api_key=api_key)

response = client.responses.create(
    model="gpt-4o-mini",
    input="Responda apenas: API da OpenAI funcionando corretamente."
)

print(response.output_text)
