"""Identidade (nome + país) dos bots do modo Clássico/Bermuda e dos bots oficiais.

O país vira bandeira em `static/flags/<código em minúsculas>.svg`. Código vazio = sem bandeira.
Tudo aqui é derivado do número do bot, então não precisa de coluna nova no banco:
para mudar o país ou o nome de um bot, edite as tabelas abaixo.
"""
from core.constants import CLASSIC_BONUS_BOTS, CLASSIC_LEGENDS, CLASSIC_OFFICIAL_BOTS

# Lendas (1–30), na mesma ordem de CLASSIC_LEGENDS.
CLASSIC_LEGEND_COUNTRIES = [
    "NO", "US", "US", "IN", "IN", "IN", "UZ", "FR", "RU", "CN", "NL", "US", "US", "FR", "CN",
    "RU", "RU", "RU", "CU", "LV", "US", "HU", "CN", "IN", "CN", "RU", "RU", "CN", "GE", "SE",
]
# Bots oficiais do Clássico (31–41), na ordem de CLASSIC_OFFICIAL_BOTS.
CLASSIC_OFFICIAL_COUNTRIES = ["BR", "BR", "BR", "BR", "BR", "BR", "BR", "BR", "", "BR", ""]
# Bots oficiais 1–12 do modo "Contra bot" (número -> país).
OFFICIAL_BOT_COUNTRIES = {1: "BR", 2: "BR", 3: "BR", 4: "BR", 5: "BR", 6: "BR", 7: "BR", 8: "BR", 9: "", 10: "BR", 11: "", 12: "BR"}
# Bots brasileiros extras (701+), na ordem de CLASSIC_BONUS_BOTS ("Alien de Gotham" é paródia americana).
CLASSIC_BONUS_COUNTRIES = ["BR", "BR", "BR", "BR", "BR", "BR", "BR", "US", "BR", "BR", "BR"]

# Países dos bots comuns (42 em diante), alternando nesta ordem.
CLASSIC_COUNTRY_ORDER = ["BR", "US", "FR", "DE", "JP", "IN", "ES", "GB", "KR", "IT", "MX", "TR", "RU", "EG", "NG", "AR", "CN", "PL", "PT", "NL", "SE"]
CLASSIC_COUNTRY_NAMES = {
    "BR": (["Rafael", "Thiago", "Larissa", "Mariana", "Gustavo", "Isadora", "Caio", "Bruna", "Leandro", "Vitória", "Heitor", "Luana"],
           ["Carvalho", "Ribeiro", "Barbosa", "Moreira", "Araújo", "Nogueira", "Teixeira", "Cavalcanti", "Monteiro", "Rocha", "Dantas", "Medeiros"]),
    "US": (["Tyler", "Madison", "Brandon", "Ashley", "Austin", "Kayla", "Logan", "Hannah", "Connor", "Brooke", "Dylan", "Savannah"],
           ["Walker", "Hughes", "Parker", "Bennett", "Coleman", "Foster", "Brooks", "Reed", "Murphy", "Cooper", "Ward", "Sullivan"]),
    "FR": (["Étienne", "Margaux", "Baptiste", "Océane", "Théo", "Clémence", "Maxime", "Inès", "Gaspard", "Capucine", "Arnaud", "Anaïs"],
           ["Lefèvre", "Fontaine", "Girard", "Rousseau", "Mercier", "Lambert", "Fournier", "Chevalier", "Beaumont", "Delacroix", "Marchand", "Vasseur"]),
    "DE": (["Maximilian", "Lena", "Tobias", "Johanna", "Felix", "Katharina", "Matthias", "Greta", "Sebastian", "Annika", "Florian", "Clara"],
           ["Kaiser", "Bauer", "Krüger", "Lehmann", "Köhler", "Brandt", "Vogel", "Hartmann", "Zimmermann", "Lorenz", "Falk", "Engel"]),
    "JP": (["Haruto", "Yuki", "Sora", "Hana", "Ren", "Mio", "Daiki", "Sakura", "Kenji", "Aoi", "Takumi", "Rin"],
           ["Tanaka", "Watanabe", "Kobayashi", "Nakamura", "Kato", "Yoshida", "Yamamoto", "Sasaki", "Matsumoto", "Inoue", "Kimura", "Hayashi"]),
    "IN": (["Arjun", "Priya", "Rohan", "Neha", "Karthik", "Ishita", "Siddharth", "Meera", "Aniket", "Tanvi", "Vikram", "Lakshmi"],
           ["Iyer", "Reddy", "Menon", "Chatterjee", "Bhatt", "Kapoor", "Desai", "Pillai", "Banerjee", "Malhotra", "Agarwal", "Naidu"]),
    "ES": (["Alejandro", "Marta", "Sergio", "Lucía", "Álvaro", "Paula", "Rubén", "Irene", "Adrián", "Noelia", "Gonzalo", "Elena"],
           ["Navarro", "Molina", "Ortega", "Castillo", "Vidal", "Herrera", "Iglesias", "Cabrera", "Paredes", "Roldán", "Salazar", "Quintana"]),
    "GB": (["Oliver", "Harry", "Charlotte", "Amelia", "George", "Poppy", "Archie", "Isla", "Freddie", "Imogen", "Alfie", "Florence"],
           ["Whitaker", "Hargreaves", "Pembroke", "Ashworth", "Thornton", "Fairfax", "Blackwood", "Holloway", "Sinclair", "Westbrook", "Gallagher", "Rutherford"]),
    "KR": (["Min-jun", "Seo-yeon", "Joon-ho", "Ji-woo", "Hyun-woo", "Ha-eun", "Dong-hyun", "Su-bin", "Tae-yang", "Yuna", "Seung-min", "Da-hye"],
           ["Kim", "Lee", "Park", "Choi", "Jung", "Kang", "Cho", "Yoon", "Jang", "Lim", "Han", "Oh"]),
    "IT": (["Lorenzo", "Giulia", "Matteo", "Chiara", "Federico", "Elisa", "Riccardo", "Francesca", "Alessio", "Valentina", "Davide", "Martina"],
           ["Rossi", "Ferrari", "Esposito", "Bianchi", "Romano", "Colombo", "Ricci", "Marino", "Greco", "Bruno", "Conti", "De Luca"]),
    "MX": (["Santiago", "Ximena", "Emiliano", "Renata", "Cuauhtémoc", "Itzel", "Mauricio", "Regina", "Axel", "Frida", "Rodolfo", "Camila"],
           ["Hernández", "Morales", "Ramírez", "Flores", "Mendoza", "Aguilar", "Villanueva", "Cervantes", "Ibarra", "Sandoval", "Guerrero", "Escobar"]),
    "TR": (["Emre", "Zeynep", "Burak", "Elif", "Kerem", "Defne", "Mert", "Selin", "Deniz", "Ece", "Onur", "Büşra"],
           ["Yılmaz", "Kaya", "Demir", "Çelik", "Aydın", "Arslan", "Doğan", "Kılıç", "Aslan", "Çetin", "Koç", "Şahin"]),
    "RU": (["Aleksei", "Svetlana", "Nikolai", "Ekaterina", "Pavel", "Olga", "Sergei", "Tatiana", "Konstantin", "Irina", "Vladislav", "Natalia"],
           ["Volkov", "Sidorov", "Orlov", "Fedorov", "Gromov", "Zaitsev", "Belov", "Medvedev", "Kiselev", "Romanov", "Antonov", "Tarasov"]),
    "EG": (["Omar", "Layla", "Karim", "Nour", "Youssef", "Salma", "Tarek", "Dina", "Hassan", "Mariam", "Khaled", "Yasmin"],
           ["Hamdy", "Farouk", "Mansour", "Nasser", "Saleh", "Ashraf", "Khalil", "Fahmy", "Samir", "Zaki", "Badawi", "Habib"]),
    "NG": (["Chidi", "Amara", "Tunde", "Ngozi", "Emeka", "Folake", "Kelechi", "Adaeze", "Segun", "Chioma", "Ifeanyi", "Yetunde"],
           ["Okafor", "Adeyemi", "Balogun", "Nwosu", "Okonkwo", "Bello", "Eze", "Adebayo", "Ogunleye", "Obi", "Ibekwe", "Afolabi"]),
    "AR": (["Facundo", "Candela", "Nicolás", "Milagros", "Joaquín", "Agustina", "Tomás", "Julieta", "Bautista", "Delfina", "Ezequiel", "Pilar"],
           ["Acosta", "Benítez", "Ferreyra", "Giménez", "Maldonado", "Peralta", "Quiroga", "Rivero", "Sosa", "Vera", "Domínguez", "Figueroa"]),
    "CN": (["Wei", "Na", "Jun", "Mei", "Hao", "Yan", "Bo", "Ling", "Chen", "Fang", "Tao", "Yue"],
           ["Wang", "Zhang", "Liu", "Huang", "Zhao", "Zhou", "Xu", "Sun", "Ma", "Zhu", "Hu", "Guo"]),
    "PL": (["Kacper", "Zofia", "Szymon", "Aleksandra", "Mateusz", "Karolina", "Jakub", "Wiktoria", "Bartosz", "Natalia", "Piotr", "Magdalena"],
           ["Nowak", "Kowalski", "Wiśniewski", "Wójcik", "Kamiński", "Lewandowski", "Zieliński", "Szymański", "Woźniak", "Dąbrowski", "Kozłowski", "Jankowski"]),
    "PT": (["Duarte", "Madalena", "Rodrigo", "Matilde", "Tiago", "Leonor", "Diogo", "Carolina", "Miguel", "Joana", "Nuno", "Mariana"],
           ["Pinto", "Machado", "Correia", "Tavares", "Cardoso", "Esteves", "Azevedo", "Matos", "Figueiredo", "Valente", "Rebelo", "Salgado"]),
    "NL": (["Daan", "Sanne", "Bram", "Lotte", "Thijs", "Fleur", "Joris", "Eva", "Sem", "Anouk", "Ruben", "Maud"],
           ["de Vries", "van Dijk", "Bakker", "Jansen", "Visser", "Smit", "Meijer", "de Boer", "Mulder", "Bos", "Vos", "Peters"]),
    "SE": (["Erik", "Astrid", "Oskar", "Freja", "Lars", "Elsa", "Viktor", "Ingrid", "Axel", "Saga", "Nils", "Maja"],
           ["Andersson", "Johansson", "Lindqvist", "Nilsson", "Eriksson", "Bergström", "Holm", "Sjöberg", "Lundgren", "Forsberg", "Nyström", "Åberg"]),
}

CLASSIC_COMMON_FIRST_NUMBER = len(CLASSIC_LEGENDS) + len(CLASSIC_OFFICIAL_BOTS) + 1
CLASSIC_COMMON_LAST_NUMBER = 700


def classic_bot_identity(bot_number: int):
    """(nome, país) do bot do Clássico `bot_number`. O nome é igual em todos os idiomas."""
    legends, officials = len(CLASSIC_LEGENDS), len(CLASSIC_OFFICIAL_BOTS)
    if bot_number <= legends:
        return CLASSIC_LEGENDS[bot_number - 1], CLASSIC_LEGEND_COUNTRIES[bot_number - 1]
    if bot_number <= legends + officials:
        index = bot_number - legends - 1
        return CLASSIC_OFFICIAL_BOTS[index][0], CLASSIC_OFFICIAL_COUNTRIES[index]
    if bot_number > CLASSIC_COMMON_LAST_NUMBER:
        index = bot_number - CLASSIC_COMMON_LAST_NUMBER - 1
        if index < len(CLASSIC_BONUS_BOTS):
            return CLASSIC_BONUS_BOTS[index][0], CLASSIC_BONUS_COUNTRIES[index]
        return f"Bot {bot_number}", ""
    index = bot_number - legends - officials - 1
    code = CLASSIC_COUNTRY_ORDER[index % len(CLASSIC_COUNTRY_ORDER)]
    position = index // len(CLASSIC_COUNTRY_ORDER)
    firsts, lasts = CLASSIC_COUNTRY_NAMES[code]
    # Combinação (posição, posição//12) evita repetir nome+sobrenome dentro do mesmo país.
    return f"{firsts[position % len(firsts)]} {lasts[(position + position // len(firsts)) % len(lasts)]}", code


def classic_bot_country(bot_number: int) -> str:
    return classic_bot_identity(bot_number)[1]
