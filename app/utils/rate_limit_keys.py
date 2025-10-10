# app/utils/rate_limit_keys.py

from fastapi import Request
from app.core.dependencies import get_current_user_id
# Não precisamos de 'typing' ou 'Callable' aqui, apenas a implementação:

# Key function para o rate limiting baseado no ID do utilizador (via JWT)
async def user_id_key_func(request: Request) -> str:
    """
    Extrai o User ID do token JWT para usar como chave de rate limiting.
    Se o token for inválido, o get_current_user_id levantará uma 401,
    impedindo o processamento do pedido e do rate limit.
    """
    # get_current_user_id necessita da Request para extrair o cabeçalho Authorization
    # O FastAPILimiter injeta a Request automaticamente nesta função.
    user_id = await get_current_user_id(request)
    return f"user_id:{user_id}"

# Key function para rate limiting baseado no IP (útil para /auth/login, etc.)
def ip_key_func(request: Request) -> str:
    """
    Usa o IP do cliente como chave (útil para rotas não autenticadas).
    """
    return request.client.host