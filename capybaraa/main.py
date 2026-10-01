from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import chess
import chess.engine
import json
import uuid
import random

app = FastAPI(title="Capybara Chess Server")

# Banco de dados temporário em memória
usuarios_db = {}
codigo_papainoel_usos = 0
salas_ativas: Dict[str, Dict] = {}

# Rota para carregar a interface Web do jogo
@app.get("/", response_class=HTMLResponse)
def carregar_jogo():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Arquivo index.html não encontrado na raiz do projeto.</h1>"

# --- REGISTRO E CÓDIGO PROMO ---
class RegistroUsuario(BaseModel):
    username: str
    password: str = Field(..., min_length=7)
    aceitou_termos: bool

@app.post("/registrar/")
def registrar_conta(dados: RegistroUsuario):
    if not dados.aceitou_termos:
        raise HTTPException(status_code=400, detail="Aceite os termos de uso.")
    if dados.username in usuarios_db:
        raise HTTPException(status_code=400, detail="Nome de usuário indisponível.")
    
    novo_id = f"capy_{len(usuarios_db) + 1}"
    usuarios_db[dados.username] = {
        "id": novo_id,
        "password": dados.password,
        "camarcoins": 100,
        "rating": None,
        "premium": False,
        "ultimo_login": datetime.now(),
        "selos": []
    }
    return {"mensagem": "Conta criada!", "id": novo_id}

@app.post("/resgatar_codigo/")
def resgatar_codigo(username: str, codigo: str):
    global codigo_papainoel_usos
    if username not in usuarios_db:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    if codigo == "papainoel2025":
        if codigo_papainoel_usos >= 4:
            raise HTTPException(status_code=400, detail="Código esgotado (máx 4 usos).")
        usuarios_db[username]["camarcoins"] += 1000
        usuarios_db[username]["premium"] = True
        codigo_papainoel_usos += 1
        return {"mensagem": "Resgatado! +1000 Camarcoins e Selo Premium."}
    raise HTTPException(status_code=400, detail="Código inválido.")

# --- WEBSOCKET DA PARTIDA ---
@app.websocket("/ws/partida/{sala_id}/{user_id}")
async def websocket_partida(websocket: WebSocket, sala_id: str, user_id: str):
    await websocket.accept()
    if sala_id not in salas_ativas:
        salas_ativas[sala_id] = {"tabuleiro": chess.Board()}
    
    tabuleiro = salas_ativas[sala_id]["tabuleiro"]
    try:
        while True:
            data = await websocket.receive_text()
            evento = json.loads(data)
            if evento["tipo"] == "lance":
                try:
                    mov = chess.Move.from_uci(evento["lance"])
                    if mov in tabuleiro.legal_moves:
                        tabuleiro.push(mov)
                        await websocket.send_text(json.dumps({
                            "tipo": "lance_executado", 
                            "fen": tabuleiro.fen(),
                            "checkmate": tabuleiro.is_checkmate()
                        }))
                    else:
                        await websocket.send_text(json.dumps({"tipo": "erro_lance", "mensagem": "LANCE ILEGAL"}))
                except ValueError:
                    await websocket.send_text(json.dumps({"tipo": "erro_lance", "mensagem": "LANCE ILEGAL"}))
    except WebSocketDisconnect:
        pass
        from fastapi import FastAPI, HTTPException
from datetime import datetime
from pydantic import BaseModel, Field

app = FastAPI(title="Capybara Chess API")

# Banco de dados simulado em memória para este passo
usuarios_db = {}
codigo_papainoel_usos = 0 # Limite de 4 usos globais

class RegistroUsuario(BaseModel):
    username: str
    password: str = Field(..., min_length=7, description="A senha deve ter 7 caracteres ou mais")
    aceitou_termos: bool

@app.post("/registrar/")
def registrar_conta(dados: RegistroUsuario):
    # 1. Verifica os termos (contas inativas por 1 mês serão deletadas)
    if not dados.aceitou_termos:
        raise HTTPException(status_code=400, detail="Você deve aceitar os termos de uso.")
    
    # 2. Impede que vários usuários usem o mesmo nome
    if dados.username in usuarios_db:
        raise HTTPException(status_code=400, detail="Nome de usuário já está em uso. Escolha outro.")
    
    # 3. Cria a conta com ID único e saldo padrão
    novo_id = f"capy_{len(usuarios_db) + 1}"
    usuarios_db[dados.username] = {
        "id": novo_id,
        "password": dados.password, # Em um ambiente real, isso deve ser criptografado
        "camarcoins": 100,
        "rating": None, # Será definido após jogar com um dos 5 primeiros bots
        "premium": False,
        "ultimo_login": datetime.now(),
        "selos": []
    }
    
    return {"mensagem": "Conta criada com sucesso! Você só pode mudar este nome pagando 30 Camarcoins.", "id": novo_id}

@app.post("/resgatar_codigo/")
def resgatar_codigo(username: str, codigo: str):
    global codigo_papainoel_usos
    
    if username not in usuarios_db:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        
    if codigo == "papainoel2025":
        if codigo_papainoel_usos >= 4:
            raise HTTPException(status_code=400, detail="Este código já atingiu o limite máximo de 4 usos.")
            
        usuario = usuarios_db[username]
        usuario["camarcoins"] += 1000
        usuario["premium"] = True
        codigo_papainoel_usos += 1
        
        return {"mensagem": "Código resgatado! Você ganhou 1000 Camarcoins e o símbolo Premium."}
    
    raise HTTPException(status_code=400, detail="Código inválido.")
    import chess
import chess.engine
from typing import Dict, Any, Optional

# Mapeamento oficial dos 11 Bots do jogo Capybara
BOTS_CONFIG: Dict[int, Dict[str, Any]] = {
    1: {"nome": "Capivarão", "rating": 500, "titulo": None, "selo": "C", "cor_selo": "vermelho", "calibravel": True},
    2: {"nome": "Pirata", "rating": 1000, "titulo": None, "selo": "P", "cor_selo": "cinza", "calibravel": True},
    3: {"nome": "Marinheiro", "rating": 1500, "titulo": None, "selo": "M", "cor_selo": "azul", "calibravel": True},
    4: {"nome": "Governador", "rating": 2000, "titulo": None, "selo": "G", "cor_selo": "roxo", "calibravel": True},
    5: {"nome": "Imperador", "rating": 2150, "titulo": None, "selo": "I", "cor_selo": "dourado", "calibravel": True},
    6: {"nome": "Pedro", "rating": 2300, "titulo": "Mestre Nacional", "selo": "NM", "cor_selo": "bronze", "calibravel": False},
    7: {"nome": "Dill", "rating": 2400, "titulo": "Mestre FIDE", "selo": "FM", "cor_selo": "prata", "calibravel": False},
    8: {"nome": "Erick", "rating": 2500, "titulo": "Mestre Internacional", "selo": "IM", "cor_selo": "ouro", "calibravel": False},
    9: {"nome": "Anonimus", "rating": 2700, "titulo": "Grande Mestre", "selo": "GM", "cor_selo": "platina", "calibravel": False},
    10: {"nome": "Super GM Camargo", "rating": 2850, "titulo": "Super Grande Mestre", "selo": "SP", "cor_selo": "dourado_especial", "calibravel": False},
    11: {"nome": "Fish", "rating": 3000, "titulo": "Stockfish", "selo": "ST", "cor_selo": "verde", "calibravel": False}
}

class BotEngine:
    def __init__(self, stockfish_path: str = "/usr/games/stockfish"):
        self.stockfish_path = stockfish_path

    def obter_lance_bot(self, tabuleiro_fen: str, bot_id: int, tempo_restante_ms: int = 1000) -> str:
        if bot_id not in BOTS_CONFIG:
            raise ValueError("Bot inválido.")
            
        bot_info = BOTS_CONFIG[bot_id]
        tabuleiro = chess.Board(tabuleiro_fen)
        
        # Conecta à engine real do Stockfish
        with chess.engine.SimpleEngine.popen_uci(self.stockfish_path) as engine:
            # Limita a força computacional para bater exatamente com o ELO do bot
            engine.configure({
                "UCI_LimitStrength": True,
                "Elo": bot_info["rating"]
            })
            
            # Limita o tempo de reflexão da máquina conforme o ritmo de jogo
            limite = chess.engine.Limit(time=min(1.0, tempo_restante_ms / 1000.0))
            resultado = engine.play(tabuleiro, limite)
            return resultado.move.uci()

def calibrar_rating_inicial(bot_id: int, resultado_match: str) -> Optional[int]:
    """
    Define o rating inicial baseado nas regras contra os bots 1 a 5:
    - Vitoria (melhor de 3): Ganha o rating integral do Bot.
    - Empate no match: Recebe (Rating do Bot - 50).
    """
    bot = BOTS_CONFIG.get(bot_id)
    if not bot or not bot["calibravel"]:
        return None # Somente bots do 1 ao 5 podem calibrar o rating inicial
        
    if resultado_match == "vitoria":
        return bot["rating"]
    elif resultado_match == "empate":
        return bot["rating"] - 50
    
    return 400 # Rating minimo padrão em caso de derrota inicial import math

def calcular_rating_cbx(rating_jogador: int, rating_oponente: int, resultado: float, total_partidas: int = 0) -> int:
    """
    Calcula a variação de Rating Elo de acordo com a regra CBX.
    
    :param rating_jogador: Pontuação atual do jogador
    :param rating_oponente: Pontuação atual do adversário
    :param resultado: 1.0 para Vitória, 0.5 para Empate, 0.0 para Derrota
    :param total_partidas: Partidas jogadas no sistema (define o Fator K)
    :return: Novo rating do jogador
    """
    # 1. Definição do Fator K da CBX
    if total_partidas < 30:
        k_factor = 40  # Enxadristas novos / em fase de calibração
    elif rating_jogador >= 2400:
        k_factor = 10  # Mestres e alto rendimento
    else:
        k_factor = 20  # Jogadores regulares
        
    # 2. Cálculo da expectativa de vitória (E)
    diferenca_rating = rating_oponente - rating_jogador
    expectativa = 1.0 / (1.0 + math.pow(10, diferenca_rating / 400.0))
    
    # 3. Atualização do Rating
    novo_rating = rating_jogador + round(k_factor * (resultado - expectativa))
    
    # Trava do limite máximo do jogo (3400)
    return min(novo_rating, 3400) from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from typing import Dict, List, Optional
import chess
import json

app = FastAPI()

# Armazenamento em memória das salas ativas e conexões
salas_ativas: Dict[str, Dict] = {}

class GerenciadorConexoes:
    def __init__(self):
        # Mapeia sala_id para lista de websockets conectados (jogadores + espectadores)
        self.conexoes_salas: Dict[str, List[WebSocket]] = {}

    async def conectar(self, websocket: WebSocket, sala_id: str):
        await websocket.accept()
        if sala_id not in self.conexoes_salas:
            self.conexoes_salas[sala_id] = []
        self.conexoes_salas[sala_id].append(websocket)

    def desconectar(self, websocket: WebSocket, sala_id: str):
        if sala_id in self.conexoes_salas:
            self.conexoes_salas[sala_id].remove(websocket)

    async def transmitir_sala(self, sala_id: str, mensagem: dict):
        if sala_id in self.conexoes_salas:
            for conexao in self.conexoes_salas[sala_id]:
                await conexao.send_text(json.dumps(mensagem))

gerenciador = GerenciadorConexoes()

def liquidar_partida_ranqueada(jogadores_db: dict, id_vencedor: str, id_perdedor: str, dif_rating: int, dif_moedas: int):
    """
    Regras econômicas de Camarcoins para partidas ranqueadas:
    - Vencer alguém 100+ de rating acima: +40 moedas. Perder para alguém 100 abaixo: perde metade.
    - Vencer alguém com diferença de 50 moedas: +20 moedas. Perder: perde metade.
    - Permite saldo negativado.
    """
    vencedor = jogadores_db[id_vencedor]
    perdedor = jogadores_db[id_perdedor]
    
    premio = 0
    if dif_rating >= 100:
        premio = 40
    elif dif_moedas >= 50:
        premio = 20
    else:
        premio = 10 # Prêmio base de vitória ranqueada
        
    vencedor["camarcoins"] += premio
    perdedor["camarcoins"] -= (premio // 2) # Perde a metade

@app.websocket("/ws/partida/{sala_id}/{user_id}")
async def websocket_partida(websocket: WebSocket, sala_id: str, user_id: str, usuarios_db: dict):
    await gerenciador.conectar(websocket, sala_id)
    
    # Se a sala não existe, inicia um novo tabuleiro e estado
    if sala_id not in salas_ativas:
        salas_ativas[sala_id] = {
            "tabuleiro": chess.Board(),
            "jogadores": [user_id],
            "espectadores": [],
            "ritmo": "3+2",
            "modo": "ranqueado",
            "historico_pgn": []
        }
    elif user_id not in salas_ativas[sala_id]["jogadores"] and len(salas_ativas[sala_id]["jogadores"]) < 2:
        salas_ativas[sala_id]["jogadores"].append(user_id)
    else:
        salas_ativas[sala_id]["espectadores"].append(user_id)

    sala = salas_ativas[sala_id]

    try:
        while True:
            data = await websocket.receive_text()
            evento = json.loads(data)
            
            # 1. Envio de Emotes por Espectadores (Custa 3 Camarcoins)
            if evento["tipo"] == "emote":
                usuario = usuarios_db.get(user_id)
                if usuario and usuario["camarcoins"] >= 3:
                    usuario["camarcoins"] -= 3
                    await gerenciador.transmitir_sala(sala_id, {
                        "tipo": "emote_recebido",
                        "autor": user_id,
                        "emoji": evento["emoji"] # raiva, felicidade, tristeza
                    })
                else:
                    await websocket.send_text(json.dumps({"tipo": "erro", "mensagem": "Camarcoins insuficientes para enviar emote."}))

            # 2. Execução de Lances no Tabuleiro
            elif evento["tipo"] == "lance":
                tabuleiro = sala["tabuleiro"]
                try:
                    movimento = chess.Move.from_uci(evento["lance"])
                    if movimento in tabuleiro.legal_moves:
                        tabuleiro.push(movimento)
                        sala["historico_pgn"].append(evento["lance"])
                        
                        eh_checkmate = tabuleiro.is_checkmate()
                        
                        await gerenciador.transmitir_sala(sala_id, {
                            "tipo": "lance_executado",
                            "fen": tabuleiro.fen(),
                            "ultimo_lance": evento["lance"],
                            "checkmate": eh_checkmate
                        })
                        
                        # Se houver checkmate, ativa fim de jogo e liquida economia
                        if eh_checkmate and sala["modo"] == "ranqueado" and len(sala["jogadores"]) == 2:
                            oponente_id = [j for j in sala["jogadores"] if j != user_id][0]
                            dif_rat = usuarios_db[oponente_id]["rating"] - usuarios_db[user_id]["rating"]
                            dif_moeda = usuarios_db[oponente_id]["camarcoins"] - usuarios_db[user_id]["camarcoins"]
                            liquidar_partida_ranqueada(usuarios_db, user_id, oponente_id, dif_rat, dif_moeda)
                    else:
                        # Alerta em vermelho no frontend
                        await websocket.send_text(json.dumps({"tipo": "erro_lance", "mensagem": "LANCE ILEGAL"}))
                except ValueError:
                    await websocket.send_text(json.dumps({"tipo": "erro_lance", "mensagem": "LANCE ILEGAL"}))

    except WebSocketDisconnect:
        gerenciador.desconectar(websocket, sala_id) from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict

router_loja = APIRouter(prefix="/loja", tags=["Loja e Personalização"])

# Catálogo oficial de Molduras (60 a 400 Camarcoins)
MOLDURAS_CATALOGO: Dict[int, Dict] = {
    1: {"nome": "Madeira BÁSICA", "preco": 60},
    2: {"nome": "Ferro Fundido", "preco": 80},
    3: {"nome": "Bronze do Peão", "preco": 120},
    4: {"nome": "Prata da Torre", "preco": 180},
    5: {"nome": "Ouro do Cavalo", "preco": 240},
    6: {"nome": "Esmeralda do Bispo", "preco": 300},
    7: {"nome": "Rubi da Rainha", "preco": 350},
    8: {"nome": "Diamante do Rei", "preco": 380},
    9: {"nome": "Neon Capivara", "preco": 390},
    10: {"nome": "Mitocôndria Dourada", "preco": 400}
}

# Catálogo de Símbolos de Guerra / Capas de Perfil (20 a 450 Camarcoins)
SIMBOLOS_GUERRA_CATALOGO: Dict[int, Dict] = {
    1: {"nome": "Escudo de Madeira", "preco": 20},
    2: {"nome": "Espadas Cruzadas", "preco": 50},
    3: {"nome": "Lança do Peão", "preco": 100},
    4: {"nome": "Muro da Torre", "preco": 150},
    5: {"nome": "Carga do Cavalo", "preco": 200},
    6: {"nome": "Feitiço do Bispo", "preco": 250},
    7: {"nome": "Coroa da Rainha", "preco": 300},
    8: {"nome": "Cetro Real", "preco": 350},
    9: {"nome": "Capivara de Guerra", "preco": 400},
    10: {"nome": "Domínio Imperial", "preco": 450}
}

class TrocaNomeRequest(BaseModel):
    novo_username: str

@router_loja.post("/mudar_nome/{username_atual}")
def mudar_nome_usuario(username_atual: str, dados: TrocaNomeRequest, usuarios_db: dict):
    if username_atual not in usuarios_db:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    
    if dados.novo_username in usuarios_db:
        raise HTTPException(status_code=400, detail="Este nome de usuário já está em uso por outra pessoa.")
        
    usuario = usuarios_db[username_atual]
    
    # Validação do custo de 30 Camarcoins
    if usuario["camarcoins"] < 30:
        raise HTTPException(status_code=400, detail="Saldo insuficiente. Mudar de nome custa 30 Camarcoins.")
        
    # Processa pagamento e libera o nome antigo
    usuario["camarcoins"] -= 30
    usuarios_db[dados.novo_username] = usuario
    del usuarios_db[username_atual]
    
    return {"mensagem": f"Nome alterado com sucesso para {dados.novo_username}! Seu nome anterior está agora disponível."}

@router_loja.post("/comprar_item/{username}")
def comprar_item_loja(username: str, tipo_item: str, item_id: int, usuarios_db: dict):
    if username not in usuarios_db:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        
    usuario = usuarios_db[username]
    catalogo = MOLDURAS_CATALOGO if tipo_item == "moldura" else SIMBOLOS_GUERRA_CATALOGO
    
    if item_id not in catalogo:
        raise HTTPException(status_code=404, detail="Item não encontrado no catálogo.")
        
    item = catalogo[item_id]
    
    if usuario["camarcoins"] < item["preco"]:
        raise HTTPException(status_code=400, detail="Camarcoins insuficientes.")
        
    usuario["camarcoins"] -= item["preco"]
    
    if "inventario" not in usuario:
        usuario["inventario"] = {"molduras": [], "simbolos": []}
        
    chave_inv = "molduras" if tipo_item == "moldura" else "simbolos"
    usuario["inventario"][chave_inv].append(item_id)
    
    return {"mensagem": f"{item['nome']} adquirido com sucesso!", "saldo_atual": usuario["camarcoins"]}
    from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router_bots = APIRouter(prefix="/api/bot", tags=["Desafio Bots"])

class DesafioBotRequest(BaseModel):
    username: str
    bot_id: int
    cor: str  # "brancas", "pretas", "aleatorio"
    ritmo: str

class ResultadoMatchBotRequest(BaseModel):
    username: str
    bot_id: int
    vitorias_jogador: int
    vitorias_bot: int
    empates: int

@router_bots.post("/finalizar_match")
def finalizar_match_bot(dados: ResultadoMatchBotRequest, usuarios_db: dict):
    if dados.username not in usuarios_db:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    
    usuario = usuarios_db[dados.username]
    bot_info = BOTS_CONFIG.get(dados.bot_id)

    if not bot_info:
        raise HTTPException(status_code=404, detail="Bot inexistente.")

    # 1. Regra especial do Bot 1 (Capivarão): Melhor de 3 partidas (precisa de 2 vitórias)
    if dados.bot_id == 1:
        if dados.vitorias_jogador >= 2:
            usuario["rating"] = 500
            if "C" not in usuario["selos"]:
                usuario["selos"].append("C")
            return {
                "mensagem": "Parabéns! Você venceu a melhor de 3 contra o Capivarão! Rating definido em 500 e Selo C desbloqueado!",
                "rating": 500,
                "selo_desbloqueado": "C"
            }

    # 2. Regra para os Bots 2 a 5 (Calibração Inicial)
    if bot_info["calibravel"]:
        if dados.vitorias_jogador > dados.vitorias_bot:
            novo_rating = bot_info["rating"]
            resultado_msg = f"Vitória! Seu rating inicial foi definido em {novo_rating}!"
        elif dados.empates > 0 and dados.vitorias_jogador == dados.vitorias_bot:
            # Empate no match: Rating do Bot - 50
            novo_rating = bot_info["rating"] - 50
            resultado_msg = f"Empate no match! Seu rating inicial foi definido em {novo_rating} (Rating - 50)!"
        else:
            novo_rating = 400
            resultado_msg = "Derrota! Seu rating inicial foi definido na pontuação de entrada (400)."

        usuario["rating"] = novo_rating
        return {"mensagem": resultado_msg, "rating": novo_rating}

    return {"mensagem": "Match contra bot concluído sem alteração de rating inicial."}
    from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
import uuid

router_social = APIRouter(prefix="/social", tags=["Social e Desafios"])

# Armazenamento de convites ativos por link
convites_link_db: Dict[str, Dict] = {}
mensagens_chat_db: Dict[str, List[Dict]] = {}

class DesafioLinkRequest(BaseModel):
    desafiante_id: str
    ritmo_customizado: str # ex: "1+0", "3+2", "10+0" ou "5+3"
    modo: str # "ranqueado" ou "classico"

class MensagemChatRequest(BaseModel):
    remetente_id: str
    destinatario_id: str
    texto: str
    partida_pgn_link: Optional[str] = None

@router_social.post("/adicionar_amigo/{user_id}/{amigo_nick}")
def adicionar_amigo(user_id: str, amigo_nick: str, usuarios_db: dict):
    if user_id not in usuarios_db or amigo_nick not in usuarios_db:
        raise HTTPException(status_code=404, detail="Usuário ou amigo não encontrado.")
    
    usuario = usuarios_db[user_id]
    amigo = usuarios_db[amigo_nick]
    
    if "amigos" not in usuario:
        usuario["amigos"] = []
    
    if amigo["id"] in usuario["amigos"]:
        raise HTTPException(status_code=400, detail="Este usuário já está na sua lista de amigos.")
        
    usuario["amigos"].append(amigo["id"])
    return {"mensagem": f"{amigo_nick} foi adicionado à sua lista de amigos!"}

@router_social.post("/gerar_link_desafio")
def gerar_link_desafio(dados: DesafioLinkRequest):
    # Gera um identificador único de 8 caracteres para o link externo
    link_token = str(uuid.uuid4())[:8]
    
    convites_link_db[link_token] = {
        "desafiante_id": dados.desafiante_id,
        "oponente_id": None, # O primeiro a clicar vai preencher este campo
        "ritmo": dados.ritmo_customizado,
        "modo": dados.modo,
        "status": "aguardando"
    }
    
    url_final = f"https://capybarachess.com/jogar?convite={link_token}"
    return {"link_token": link_token, "url_compartilhavel": url_final}

@router_social.get("/entrar_por_link/{link_token}/{jogador_id}")
def entrar_por_link(link_token: str, jogador_id: str):
    if link_token not in convites_link_db:
        raise HTTPException(status_code=404, detail="Link de desafio inválido ou expirado.")
        
    convite = convites_link_db[link_token]
    
    if convite["status"] != "aguardando":
        raise HTTPException(status_code=400, detail="Outro jogador já aceitou este desafio!")
        
    if convite["desafiante_id"] == jogador_id:
        return {"status": "aguardando", "mensagem": "Aguardando um oponente clicar no seu link..."}
        
    # O primeiro jogador a clicar entra na partida
    convite["oponente_id"] = jogador_id
    convite["status"] = "em_andamento"
    
    return {
        "status": "iniciada",
        "sala_id": f"sala_link_{link_token}",
        "desafiante": convite["desafiante_id"],
        "ritmo": convite["ritmo"]
    }
    from fastapi import APIRouter, HTTPException, BackgroundTasks
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import random

router_sistema = APIRouter(prefix="/sistema", tags=["Sistema e Matchmaking"])

# Fila global de busca de partidas
fila_matchmaking: List[Dict] = []

# --- 1. ROTINA DE EXCLUSÃO DE CONTAS INATIVAS (> 30 DIAS) ---
def expurgar_contas_inativas(usuarios_db: dict):
    """
    Varre o banco de dados e deleta contas que não fazem login há mais de 30 dias,
    cumprindo os termos de uso aceitos pelo usuário.
    """
    agora = datetime.now()
    limite_inatividade = timedelta(days=30)
    
    contas_para_deletar = [
        username for username, dados in usuarios_db.items()
        if (agora - dados.get("ultimo_login", agora)) > limite_inatividade
    ]
    
    for username in contas_para_deletar:
        del usuarios_db[username]

@router_sistema.post("/executar_limpeza_seguranca")
def disparar_limpeza_manual(background_tasks: BackgroundTasks, usuarios_db: dict):
    background_tasks.add_task(expurgar_contas_inativas, usuarios_db)
    return {"mensagem": "Rotina de exclusão de contas inativas disparada em segundo plano."}


# --- 2. MOTOR DE MATCHMAKING COM FILTRO DE RATING ---
RITMOS_PERMITIDOS = ["1+0", "1+1", "3+0", "3+2", "10+0", "10+3", "aleatorio"]

@router_sistema.post("/entrar_fila")
def entrar_fila_matchmaking(
    username: str, 
    ritmo_escolhido: str, 
    modo: str, # "ranqueado" ou "classico"
    diferenca_maxima_rating: int, # Máximo 400 ELO
    usuarios_db: dict
):
    if username not in usuarios_db:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        
    if ritmo_escolhido not in RITMOS_PERMITIDOS:
        raise HTTPException(status_code=400, detail="Ritmo de jogo inválido.")
        
    # Trava do filtro de rating: Máximo 400 ELO de distância
    if diferenca_maxima_rating > 400:
        diferenca_maxima_rating = 400

    usuario = usuarios_db[username]
    rating_atual = usuario.get("rating") or 400

    # Trata ritmo aleatório
    if ritmo_escolhido == "aleatorio":
        ritmo_real = random.choice(["1+0", "1+1", "3+0", "3+2", "10+0", "10+3"])
    else:
        ritmo_real = ritmo_escolhido

    # Procura um oponente compatível na fila
    for jogador_espera in fila_matchmaking:
        if jogador_espera["username"] == username:
            continue

        rating_oponente = jogador_espera["rating"]
        diff_elo = abs(rating_atual - rating_oponente)

        # Valida a faixa de rating até o teto de 3400 ELO e compatibilidade de modo
        if (diff_elo <= diferenca_maxima_rating and 
            jogador_espera["modo"] == modo and 
            (jogador_espera["ritmo"] == ritmo_real or jogador_espera["ritmo_original"] == "aleatorio")):
            
            # Remove oponente da fila e cria a sala
            fila_matchmaking.remove(jogador_espera)
            sala_id = f"match_{username}_{jogador_espera['username']}"
            
            return {
                "status": "partida_encontrada",
                "sala_id": sala_id,
                "oponente": jogador_espera["username"],
                "ritmo": ritmo_real,
                "modo": modo
            }

    # Se não achar oponente instantâneo, entra na fila
    fila_matchmaking.append({
        "username": username,
        "rating": min(rating_atual, 3400), # Trava de teto CBX/Capybara (3400)
        "ritmo": ritmo_real,
        "ritmo_original": ritmo_escolhido,
        "modo": modo,
        "max_diff": diferenca_maxima_rating
    })

    return {"status": "aguardando_na_fila", "mensagem": "Buscando oponente na faixa de rating..."}