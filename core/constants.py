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
    (1, 'Vence a primeira partida', 1, 20), (2, 'Vence uma partida em Blitz', 1, 25), (3, 'Vence uma partida em Bullet', 1, 25), (4, 'Vence uma partida em Rápida', 1, 25), (5, 'Vence uma partida com precisão', 1, 40),
    (6, 'Joga três partidas', 3, 30), (7, 'Vence dois bots consecutivos', 2, 45), (8, 'Vence um bot com rating 200+ acima', 1, 80), (9, 'Vence com brancas', 1, 35), (10, 'Vence com pretas', 1, 35),
    (11, 'Completa a calibração de 2 partidas', 1, 50), (12, 'Chega ao top 500 do ranking', 1, 60), (13, 'Chega ao top 400 do ranking', 1, 70), (14, 'Chega ao top 300 do ranking', 1, 85), (15, 'Chega ao top 200 do ranking', 1, 100),
    (16, 'Chega ao top 100 do ranking', 1, 150), (17, 'Chega ao top 50 do ranking', 1, 220), (18, 'Chega ao top 10 do ranking', 1, 350), (19, 'Chega ao top 3 do ranking', 1, 500), (20, 'Vence Fish em Rápida', 1, 150),
    (21, 'Vence Fish em Blitz', 1, 150), (22, 'Vence Fish em Bullet', 1, 150), (23, 'Vence um GM em Rápida', 1, 100), (24, 'Vence um GM em Blitz', 1, 100), (25, 'Vence um GM em Bullet', 1, 100),
    (26, 'Vence Magnus Carlsen', 1, 250), (27, 'Vence Rafachess', 1, 100), (28, 'Vence três partidas consecutivas', 3, 250), (29, 'Funda ou entra em um clube', 1, 100), (30, 'Vence um desafio de clube', 1, 150)
]
