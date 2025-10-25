import logging
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from math import radians

import asyncpg
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import haversine_distances

from app.schemas.pattern_schemas import PatternModel, PatternLocation
from app.utils import parse_db_response # Usamos o utilitário para tratar respostas DB

logger = logging.getLogger(__name__)

# --- Parâmetros de Treino da IA ---
# DBSCAN precisa que a distância (eps) seja em radianos se usarmos a métrica haversine
# 0.0001 radianos é aproximadamente 0.637 metros. 
# O raio da Terra é ~6371km. 1 metro é 1/6371000 radianos.
# Para um EPS de 5 metros: 5 / 6371000 = 0.00000078 radianos.
# Vamos usar um valor razoável para a precisão do GPS interno (ex: 10 metros)
EARTH_RADIUS_KM = 6371
EPS_METERS = 10  # Raio de agrupamento de 10 metros
# Conversão de 10 metros para Radianos
EPS_RADIANS = EPS_METERS / (EARTH_RADIUS_KM * 1000) 
MIN_SAMPLES = 5  # Mínimo de 5 pontos de localização para formar um cluster
TRAINING_PERIOD_DAYS = 30 # Usar 30 dias de dados históricos

async def get_raw_location_data(conn: asyncpg.Connection, monitored_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Busca os dados de localização dos últimos 30 dias para o utilizador monitorizado.
    """
    query = """
    SELECT 
        latitude, 
        longitude, 
        created_at 
    FROM 
        core.location 
    WHERE 
        monitored_id = $1 
        AND created_at >= $2 
    ORDER BY 
        created_at ASC;
    """
    start_date = datetime.now() - timedelta(days=TRAINING_PERIOD_DAYS)
    
    try:
        records = await conn.fetch(query, monitored_id, start_date)
        # Converte os registros para uma lista de dicionários
        return [dict(r) for r in records]
    except Exception as e:
        logger.error(f"Erro ao buscar dados de localização brutos para {monitored_id}: {e}")
        return None

def analyze_clusters(df_data: pd.DataFrame) -> List[PatternLocation]:
    """
    Analisa os clusters (locais) resultantes do DBSCAN para determinar
    o centroide e as janelas de tempo de rotina.
    """
    locations: List[PatternLocation] = []

    # Iterar sobre cada cluster identificado, excluindo o ruído (-1)
    for label in df_data['cluster_label'].unique():
        if label == -1:
            continue
            
        cluster_data = df_data[df_data['cluster_label'] == label].copy()
        
        # 1. Calcular Centroide
        # O DBSCAN foi executado com coordenadas em Radianos, mas o centroide deve ser armazenado em Graus
        # Portanto, convertemos a média dos radianos de volta para graus.
        centroid_lat = np.degrees(cluster_data['lat_rad'].mean())
        centroid_lon = np.degrees(cluster_data['lon_rad'].mean())

        # 2. Análise de Séries Temporais (Janelas de Rotina)
        
        # Converte 'created_at' para o número de segundos desde a meia-noite (para análise cíclica de tempo)
        cluster_data['time_in_seconds'] = cluster_data['created_at'].dt.hour * 3600 + \
                                          cluster_data['created_at'].dt.minute * 60 + \
                                          cluster_data['created_at'].dt.second
        
        # Para simplificar na Fase 1, calculamos a janela de tempo mais comum:
        # Agrupamos as observações por hora para encontrar as horas de maior frequência
        
        # Encontra a hora mais comum (pico de atividade no local)
        most_common_hour = cluster_data['created_at'].dt.hour.mode()
        if most_common_hour.empty:
            continue # Se o cluster for muito pequeno ou problemático

        # Define uma janela simples de 2 horas em torno da hora mais comum (ajustável)
        peak_hour = most_common_hour.iloc[0]
        
        # Janela de tempo (ex: 7:00-9:00 se o pico for 8h)
        start_hour = (peak_hour - 1) % 24
        end_hour = (peak_hour + 1) % 24

        # 3. Mapeamento para PatternLocation
        location = PatternLocation(
            cluster_id=int(label),
            name=f"Local {int(label) + 1}", # Nome genérico inicial
            latitude=centroid_lat,
            longitude=centroid_lon,
            # Tempo de rotina: HH:MM:SS
            start_time=f"{start_hour:02d}:00:00",
            end_time=f"{end_hour:02d}:00:00",
            frequency=len(cluster_data) # Número de pontos no cluster
        )
        locations.append(location)

    return locations


async def train_user_patterns(db_pool: asyncpg.Pool, user_id: str) -> Dict[str, Any]:
    """
    Função principal para treinar o modelo de rotina de IA para um utilizador.
    """
    logger.info(f"Iniciando treino de padrões de IA para o utilizador: {user_id}")
    
    async with db_pool.acquire() as conn:
        # Buscar dados brutos
        raw_data = await get_raw_location_data(conn, user_id)

    if not raw_data or len(raw_data) < MIN_SAMPLES * 2:
        return {"status": "error", "message": "Dados insuficientes para treino. São necessários pelo menos 10 pontos de localização nos últimos 30 dias."}

    # Criar DataFrame para manipulação
    df = pd.DataFrame(raw_data)

    # 1. Pré-processamento: Converter graus para radianos para o cálculo da distância Haversine
    df['lat_rad'] = np.radians(df['latitude'])
    df['lon_rad'] = np.radians(df['longitude'])
    
    # Prepara os dados para o DBSCAN: Array [Latitude_rad, Longitude_rad]
    X = df[['lat_rad', 'lon_rad']].values

    # 2. Aplicar o DBSCAN para agrupamento espacial
    try:
        # Usar a métrica haversine que requer coordenadas em radianos.
        # eps é o raio máximo da vizinhança para as amostras.
        db = DBSCAN(
            eps=EPS_RADIANS, 
            min_samples=MIN_SAMPLES, 
            metric='haversine',
            n_jobs=-1 # Usa todos os núcleos disponíveis
        ).fit(X)
        
        df['cluster_label'] = db.labels_

    except Exception as e:
        logger.error(f"Erro durante a execução do DBSCAN: {e}")
        return {"status": "error", "message": f"Erro interno na execução do DBSCAN: {e}"}

    # 3. Analisar os Clusters e Determinar os Padrões
    locations = analyze_clusters(df)

    if not locations:
        return {"status": "success", "message": "Treino concluído. Não foram identificados padrões de rotina (ruído excessivo)."}

    # 4. Formatar o resultado no Schema PatternModel
    pattern_model = PatternModel(
        monitored_id=user_id,
        locations=locations,
        trained_at=datetime.now()
    )

    # 5. Persistir o Modelo na Base de Dados (JSONB)
    async with db_pool.acquire() as conn:
        try:
            # O modelo PatternModel precisa ser convertido para uma string JSON antes de ser passado
            # para a função de API do PostgreSQL.
            pattern_json_string = pattern_model.model_dump_json(indent=2)
            
            # Chama a função de API que guarda no core.user_patterns (upsert)
            result = await conn.fetchval(
                "SELECT api.upsert_user_pattern_api($1, $2)",
                user_id,
                pattern_json_string
            )
            
            # Usar o utilitário para analisar a resposta do DB
            db_response = parse_db_response(result)

            if db_response.get("status") == "success":
                logger.info(f"Padrões de IA persistidos com sucesso para {user_id}. {len(locations)} locais identificados.")
                return {"status": "success", "message": f"Padrões de rotina (Fase 1) treinados com sucesso. {len(locations)} locais identificados."}
            else:
                logger.error(f"Erro ao persistir padrões no DB: {db_response.get('message')}")
                return {"status": "error", "message": f"Erro ao persistir o modelo de IA: {db_response.get('message')}"}
            
        except Exception as e:
            logger.error(f"Erro de DB ao guardar padrões de IA: {e}")
            return {"status": "error", "message": f"Erro crítico ao persistir o modelo na base de dados."}
