BOT_SEALS = {
    'C': 'Capivarão', 'P': 'Pirata', 'M': 'Marinheiro', 'G': 'Governador',
    'I': 'Imperador', 'NM': 'Pedro', 'FM': 'Dill', 'IM': 'Erick',
    'GM': 'Anonimus', 'SP': 'Camargo', 'ST': 'Fish', 'RF': 'Rafachess'
}

SHOP_ITEMS = {
    'frame_oak': 60, 'frame_bronze': 80, 'frame_steel': 100, 'frame_marble': 130,
    'frame_royal': 160, 'frame_ruby': 200, 'frame_emerald': 240, 'frame_sapphire': 280,
    'frame_obsidian': 340, 'frame_crown': 400, 'banner_pawn': 20, 'banner_knight': 50,
    'banner_bishop': 80, 'banner_rook': 130, 'banner_queen': 180, 'banner_king': 220,
    'banner_check': 280, 'banner_mate': 320, 'banner_knights': 380, 'banner_grandmaster': 450,
    'skin_emerald': 120, 'skin_ice': 160, 'skin_sunset': 200,
}

PROMO_CODES = {
    'codigoliberatudo': {
        'type': 'unlock_all',
        'admin_only': True,
        'description': 'Desbloqueio de todo o catálogo da loja (Restrito ao Administrador)'
    },
    'capybara123': {
        'type': 'coins',
        'amount': 100,
        'max_global_uses': 40,
        'admin_only': False,
        'description': '+100 Camarcoins de Bônus da Capivara'
    },
    'papainoel2025': {
        'type': 'coins',
        'amount': 1000,
        'max_global_uses': 4,
        'admin_only': False,
        'description': '+1000 Moedas e Selo Especial de Natal'
    },
    'gmcamarguinho': {
        'type': 'unlock_all',
        'admin_only': False,
        'max_global_uses': None,
        'description': 'Todos os cosméticos liberados'
    }
}

CLAN_BADGES = {
    1: {"name": "Capivara Dourada", "icon": "🛡️"},
    2: {"name": "Lâminas Cruzadas", "icon": "⚔️"},
    3: {"name": "Coroa Real", "icon": "👑"},
    4: {"name": "Fortaleza de Pedra", "icon": "🏰"},
    5: {"name": "Águia Estrategista", "icon": "🦅"},
    6: {"name": "Lobo das Sombras", "icon": "🐺"},
    7: {"name": "Dragão Lendário", "icon": "🐉"},
    8: {"name": "Relâmpago Tático", "icon": "⚡"},
    9: {"name": "Diamante Mestre", "icon": "💎"},
    10: {"name": "Leão Imperial", "icon": "🦁"}
}

CLASSIC_LEGENDS = [
    "Magnus Carlsen", "Hikaru Nakamura", "Fabiano Caruana", "Arjun Erigaisi", "Gukesh Dommaraju", "R Praggnanandhaa",
    "Nodirbek Abdusattorov", "Alireza Firouzja", "Ian Nepomniachtchi", "Wei Yi", "Anish Giri", "Wesley So",
    "Levon Aronian", "Maxime Vachier-Lagrave", "Ding Liren", "Vladimir Kramnik", "Garry Kasparov", "Anatoly Karpov",
    "José Raúl Capablanca", "Mikhail Tal", "Bobby Fischer", "Judit Polgar", "Hou Yifan", "Koneru Humpy",
    "Ju Wenjun", "Aleksandra Goryachkina", "Kateryna Lagno", "Tan Zhongyi", "Nana Dzagnidze", "Pia Cramling",
]

CLASSIC_OFFICIAL_BOTS = [
    ("Capivarão", 500), ("Pirata", 1000), ("Marinheiro", 1500), ("Governador", 2100), ("Imperador", 2150),
    ("Pedro", 2300), ("Dill", 2400), ("Erick", 2500), ("Anonimus", 2700), ("Camargo", 2850), ("Fish", 3000),
]

CLASSIC_FIRST_NAMES = {
    "pt": ["Ana", "Beatriz", "Camila", "Diego", "Eduardo", "Fernanda", "Gabriel", "Helena", "Igor", "Julia"],
    "en": ["Ava", "Emily", "Grace", "Henry", "Jack", "Liam", "Mia", "Noah", "Olivia", "William"],
    "es": ["Ana", "Carlos", "Carmen", "Diego", "Elena", "Javier", "Lucía", "Mateo", "Sofía", "Valentina"],
    "fr": ["Amélie", "Antoine", "Camille", "Chloé", "Émile", "Hugo", "Juliette", "Léa", "Louis", "Manon"],
    "ru": ["Aleksandr", "Mikhail", "Ivan", "Dmitry", "Daniil", "Anna", "Maria", "Elena", "Daria", "Sofia"],
    "de": ["Lukas", "Leon", "Finn", "Jonas", "Elias", "Mia", "Emma", "Hannah", "Sophia", "Anna"],
    "hi": ["Aarav", "Vihaan", "Vivaan", "Reyansh", "Aditya", "Ananya", "Diya", "Saanvi", "Pari", "Kiara"],
}

CLASSIC_LAST_NAMES = {
    "pt": ["Silva", "Santos", "Oliveira", "Souza", "Costa", "Pereira", "Lima", "Almeida", "Ferreira", "Gomes"],
    "en": ["Smith", "Johnson", "Brown", "Taylor", "Wilson", "Davis", "Clark", "Evans", "Harris", "Martin"],
    "es": ["García", "Rodríguez", "López", "Martínez", "Sánchez", "Pérez", "Gómez", "Díaz", "Torres", "Ruiz"],
    "fr": ["Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard", "Petit", "Durand", "Leroy", "Moreau"],
    "ru": ["Ivanov", "Smirnov", "Kuznetsov", "Popov", "Sokolov", "Lebedev", "Kozlov", "Novikov", "Morozov", "Petrov"],
    "de": ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz", "Hoffmann"],
    "hi": ["Sharma", "Verma", "Gupta", "Patel", "Singh", "Kumar", "Rao", "Joshi", "Mishra", "Nair"],
}

CLASSIC_STYLES = ["Tático", "Posicional", "Agressivo", "Defensivo", "Técnico", "Criativo", "Sólido"]
CLASSIC_MODES = {'bullet': 'Bullet', 'blitz': 'Blitz', 'rapid': 'Rapid'}

MISSION_DEFINITIONS = [
    (1, 'Vença sua primeira partida', 1, 10, 'Fácil', 'wins'),
    (2, 'Vença uma partida Blitz', 1, 10, 'Fácil', 'wins_blitz'),
    (3, 'Vença uma partida Bullet', 1, 10, 'Fácil', 'wins_bullet'),
    (4, 'Vença uma partida Rápida', 1, 12, 'Fácil', 'wins_rapid'),
    (5, 'Vença duas partidas', 2, 14, 'Fácil', 'wins'),
    (6, 'Jogue três partidas', 3, 12, 'Fácil', 'games'),
    (7, 'Vença duas partidas com pretas', 2, 18, 'Fácil', 'wins_black'),
    (8, 'Supere seu rating: vença um bot 200+ acima', 1, 35, 'Difícil', 'upset_wins'),
    (9, 'Vença com as brancas', 1, 8, 'Fácil', 'wins_white'),
    (10, 'Vença com as pretas', 1, 8, 'Fácil', 'wins_black'),
    (11, 'Jogue cinco partidas Blitz', 5, 15, 'Média', 'games_blitz'),
    (12, 'Jogue cinco partidas Rápidas', 5, 18, 'Média', 'games_rapid'),
    (13, 'Vença três partidas', 3, 20, 'Média', 'wins'),
    (14, 'Vença cinco partidas', 5, 25, 'Média', 'wins'),
    (15, 'Empate uma partida', 1, 8, 'Fácil', 'draws'),
    (16, 'Vença um bot com rating 1000+', 1, 18, 'Média', 'wins_1000'),
    (17, 'Vença um bot com rating 1500+', 1, 25, 'Média', 'wins_1500'),
    (18, 'Vença três partidas com pretas', 3, 25, 'Média', 'wins_black'),
    (19, 'Vença três partidas com brancas', 3, 25, 'Média', 'wins_white'),
    (20, 'Vença por xeque-mate', 1, 20, 'Média', 'checkmate_wins'),
    (21, 'Vença em até 20 lances seus', 1, 20, 'Média', 'quick_wins'),
    (22, 'Promova um peão em uma partida', 1, 18, 'Média', 'promotion_games'),
    (23, 'Capture cinco ou mais peças em uma partida', 1, 20, 'Média', 'capture_rich_games'),
    (24, 'Faça roque em uma partida', 1, 12, 'Fácil', 'castling_games'),
    (25, 'Dê xeque pelo menos três vezes em uma partida', 1, 18, 'Média', 'check_games'),
    (26, 'Vença um bot com rating 2000+', 1, 35, 'Difícil', 'wins_2000'),
    (27, 'Jogue 25 partidas', 25, 40, 'Difícil', 'games'),
    (28, 'Vença dez partidas', 10, 45, 'Difícil', 'wins'),
    (29, 'Vença uma partida sem capturar peças', 1, 30, 'Difícil', 'no_capture_wins'),
    (30, 'Vença de pretas um bot com rating 2000+', 1, 50, 'Difícil', 'black_wins_2000'),
]
