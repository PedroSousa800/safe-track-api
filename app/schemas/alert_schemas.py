from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional

# -----------------------------------------------------------
# 1. Schema para Atualização (PUT) dos Parâmetros de Alerta
# -----------------------------------------------------------

class AlertParametersUpdate(BaseModel):
    """
    Schema para o corpo da requisição de atualização dos parâmetros de alerta.
    Estes parâmetros são definidos pelo Monitor para o Utilizador Monitorado.
    """
    monitored_user_id: UUID = Field(
        ...,
        description="ID do utilizador monitorado cujos parâmetros estão a ser definidos."
    )
    tolerance_minutes: int = Field(
        30,
        ge=5,
        description="Tempo máximo (em minutos) que o idoso pode estar fora do seu padrão de rotina antes de disparar um alerta. Mínimo de 5 minutos."
    )
    min_movement_meters: int = Field(
        10,
        ge=1,
        description="Distância mínima (em metros) de movimento para ser considerado um local 'válido' e não ruído de GPS. Mínimo de 1 metro."
    )
    
# -----------------------------------------------------------
# 2. Schema para Resposta (GET) dos Parâmetros de Alerta
# -----------------------------------------------------------

class AlertParametersResponse(BaseModel):
    """
    Schema para a resposta de obtenção dos parâmetros de alerta.
    """
    status: str = Field(..., description="Status da operação (success, not_found, error).")
    tolerance_minutes: int = Field(..., description="Tempo de tolerância atual em minutos.")
    min_movement_meters: int = Field(..., description="Movimento mínimo em metros.")
    message: Optional[str] = Field(None, description="Mensagem de contexto, usada se estiver a usar valores predefinidos.")
