import json
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

# --- Submodelo para um Local (Cluster) ---
class PatternLocation(BaseModel):
    """
    Define um local de rotina identificado pelo algoritmo DBSCAN (um cluster).
    Isto representa um local como 'Cozinha' ou 'Quarto'.
    """
    cluster_id: int = Field(..., description="ID único do cluster/local.")
    name: str = Field(..., description="Nome do local (ex: 'Local 1', 'Cozinha').")
    latitude: float = Field(..., description="Latitude do centroide do local.")
    longitude: float = Field(..., description="Longitude do centroide do local.")
    start_time: str = Field(..., description="Hora de início mais provável de permanência no local (HH:MM:SS).")
    end_time: str = Field(..., description="Hora de fim mais provável de permanência no local (HH:MM:SS).")
    frequency: int = Field(..., description="Número de pontos de localização usados para definir este local.")


# --- Modelo Principal do Padrão de Rotina ---
class PatternModel(BaseModel):
    """
    O Modelo de Rotina completo, que é armazenado na tabela core.user_patterns.
    """
    monitored_id: str = Field(..., description="ID do utilizador monitorizado a que o padrão se refere.")
    locations: List[PatternLocation] = Field(..., description="Lista de locais de rotina identificados.")
    trained_at: datetime = Field(..., description="Carimbo temporal da última vez que o modelo foi treinado.")
    
    # Adicionar um método para ajudar a exportar para JSON (útil para o DB)
    def model_dump_json(self, *args, **kwargs) -> str:
        """
        Retorna a representação JSON do modelo.
        """
        # Utiliza o método padrão, garantindo que as datas são serializadas corretamente
        return super().model_dump_json(by_alias=True, indent=2)
