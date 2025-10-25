import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

def parse_db_response(json_string: Optional[str]) -> Dict[str, Any]:
    """
    Função utilitária para desserializar as respostas JSON do PostgreSQL
    (que são frequentemente devolvidas como strings JSON).
    
    Args:
        json_string: A string JSON devolvida pela função do DB.

    Returns:
        Um dicionário Python (Dict[str, Any]).
    """
    if not json_string:
        return {"status": "error", "message": "Resposta vazia ou nula da base de dados."}
    
    try:
        # A resposta fetchval do asyncpg é uma string JSON, por isso é necessário o json.loads
        return json.loads(json_string)
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao analisar JSON da DB: {e}. String: {json_string[:100]}...")
        return {"status": "error", "message": "Erro na desserialização da resposta JSON da base de dados."}
