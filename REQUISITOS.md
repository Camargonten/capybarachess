# Requisitos e Arquitetura Técnica

## Objetivo

Capybara Chess é uma aplicação web de xadrez com partidas contra bots, partidas PvP online, rankings, perfis, amizades, clubes, missões e cosméticos. O cliente deve funcionar em desktop e dispositivos móveis, com navegação por clique, toque e arraste quando suportado pelo tabuleiro.

## Arquitetura

- `xadrez.py`: application factory Flask, configuração da sessão, inicialização do banco e registro dos blueprints.
- `core/config.py`: configuração por variáveis de ambiente, caminhos de banco e executável Stockfish.
- `core/db.py`: conexões SQLite, transações, WAL e migrações aditivas de colunas.
- `core/security.py`: rate limiting, validação de entrada, cabeçalhos HTTP e verificação de propriedade de conta.
- `core/engine.py`: regras e integração Stockfish, incluindo seleção de lance para bots.
- `core/constants.py`: catálogo de cosméticos, selos, missões e outras constantes do domínio.
- `blueprints/auth.py`: registro, login, logout, OAuth e payload de perfil inicial.
- `blueprints/game.py`: criação e estado de partidas, lances, relógios, resultados, rating e timeout.
- `blueprints/analysis.py`: avaliação de posição e classificação de lances.
- `blueprints/social.py`: rankings, consulta de perfil/histórico, amizades, notificações, mensagens e clubes.
- `blueprints/user.py`: perfil, bio, avatar, configurações, cosméticos, loja, missões e recompensas.
- `templates/index.html/index.html`: cliente responsivo, controles, tabuleiro e integração com a API.
- `static/`: peças SVG, avatares, manifesto e service worker.

## Persistência e sessão

SQLite é o armazenamento atual. `DATABASE_PATH` seleciona o arquivo; o Render Free está configurado para testes online em `/tmp/capybara.db`, que é efêmero e pode ser apagado em reinicializações ou deploys. Dados que precisem sobreviver exigem armazenamento persistente. O serviço definido em `render.yaml` usa Docker/Gunicorn, um worker e quatro threads. As migrações em `init_db()` devem ser aditivas e manter valores padrão para contas antigas.

A sessão Flask identifica o usuário autenticado. Endpoints de escrita devem derivar a identidade da sessão, validar os dados recebidos e usar consultas parametrizadas. Não confiar em nomes de usuário enviados pelo cliente para autorizar ações privadas.

## Fluxos Principais

### Conta e perfil

1. O cliente envia cadastro ou login para o blueprint de autenticação.
2. O servidor valida a conta, cria/consulta o perfil e responde com dados usados pelo lobby.
3. O perfil permite nome de exibição, bio de até 30 caracteres, avatar e preferências.
4. A primeira alteração do nome de exibição é gratuita; cada alteração posterior custa 100 moedas, debitadas atomicamente após validar o saldo.

### Partidas

1. O jogador escolhe modo, cor, ritmo e adversário.
2. Contas novas concluem duas partidas de calibração contra os bots oficiais 1–5 antes de acessar os modos Clássico ou PvP ranqueado. O servidor valida o estado da conta, fixa os ratings desses bots e calcula o rating a partir do resultado persistido da partida.
3. O servidor cria a partida e fornece FEN, participantes e relógios.
4. O cliente atualiza o tabuleiro de forma responsiva e envia lances UCI.
5. O servidor valida regras e relógios, atualiza a posição e retorna o estado autoritativo.
6. A análise posterior consulta a engine sem alterar o resultado da partida.

### Tutorial, modos clássicos e ranqueados

1. No primeiro acesso, o Guia da Capivara restringe a navegação às seções indicadas. Cada etapa exige abrir seu destino; o tutorial pode ser dispensado pelo botão explícito “Pular tutorial”. Progresso e conclusão ficam no armazenamento local por conta.
2. Após a calibração, o modo Clássico escolhe bots do catálogo individual cujo rating é próximo do rating clássico do jogador. O rating clássico é atualizado no servidor a partir do resultado final da partida e permanece separado do rating FIDE global.
3. O modo Rankeado usa fila PvP persistida em SQLite. Jogadores calibrados com o mesmo ritmo são pareados pelo rating e a faixa de busca aumenta gradualmente enquanto aguardam.
4. A entrada direta em partida ranqueada também exige calibração. Desafios por link direto são casuais e não alteram rating.
5. A fila depende do mesmo SQLite usado pelo aplicativo. No Render Free de teste, `DATABASE_PATH=/tmp/capybara.db`; fila e contas podem se perder com o filesystem efêmero.

### Força e tempo de pensamento dos bots

1. O motor Stockfish mapeia o rating efetivo para 16 tiers entre 500 e 3000 Elo. Ratings fora dessa faixa são limitados antes de criar a partida.
2. Os seis tiers até 1250 usam níveis crescentes de `Skill Level`; do tier 7 (1400 Elo) em diante, usam `UCI_LimitStrength`/`UCI_Elo`. Stockfish 17 rejeita `UCI_Elo` abaixo de 1320, por isso os níveis iniciais não usam essa opção.
3. O tempo normal de busca cresce por tier, de 300 ms a 3000 ms. Com 10 segundos ou menos no relógio do bot, a busca é reduzida a 1 ms.
4. Se o motor não iniciar ou não produzir um lance legal, a partida retorna erro de motor; não se substitui o resultado por um lance aleatório.

### Missões e economia

1. O catálogo possui 30 objetivos offline separados entre Fácil, Média e Difícil, com recompensas de 8 a 50 moedas.
2. Partidas contra bots atualizam progresso após resultado normal, desistência, timeout ou empate aceito. Os objetivos usam o resultado, o ritmo, a cor do jogador e o histórico SAN/UCI da partida.
3. A missão concluída expõe um resgate explícito; o servidor valida o estado e credita a recompensa uma única vez dentro de uma transação SQLite.
4. Vitórias contra bots rendem 3 moedas em Bullet, 5 em Blitz e 8 em Rápida; empates rendem 1, 1 e 2 moedas, respectivamente. Partidas customizadas seguem a recompensa Blitz. Perdas não rendem moedas.

### Social

Ranking abre o perfil público de um jogador. O perfil informa bio e partidas concluídas. Pedidos de amizade são persistidos, expostos em notificações e podem ser aceitos ou recusados; conversas são permitidas após aceite. Amigos podem listar partidas ativas e assistir em modo somente leitura. O endpoint de estado só permite espectadores autenticados com amizade aceita a um participante; espectadores não enviam lance, oferta de empate, desistência ou timeout. Para contas cadastradas, as mutações de partida usam a identidade da sessão e rejeitam usernames fornecidos para impersonação; timeout exibido ao espectador é calculado sem persistir a partida.

Partidas têm estado independente por `game_id` em SQLite. Testes de integração devem manter pares simultâneos isolados e validar que operações numa partida não alteram o FEN/histórico de outra.

### Cosméticos

Compras são validadas no servidor contra o catálogo. Inventário e item equipado persistem no perfil. Skins de peça alteram a apresentação dos SVGs no cliente sem substituir os assets locais.
URLs de peças e avatares são geradas por `url_for('static', ...)` no template para respeitar prefixos WSGI.

## Interface, acessibilidade e internacionalização

- O tabuleiro suporta drag-and-drop do chessboard.js e seleção de origem/destino por clique ou toque.
- `moveSpeed` controla a duração da transição de peça: 160 ms, com movimento instantâneo quando `prefers-reduced-motion: reduce` estiver ativo.
- O modo daltônico deve manter contraste nas casas claras e escuras em tabuleiros de jogo e análise.
- A BGM usa Web Audio API, respeita a preferência local e não toca durante uma partida. Abrir configurações não deve parar a sequência.
- Locales disponíveis: português (`pt`), inglês (`en`), espanhol (`es`), francês (`fr`), russo (`ru`), alemão (`de`) e hindi (`hi`). Novos textos de interface devem entrar no catálogo de traduções ou usar uma chave de tradução; valores dinâmicos devem ser localizados no ponto de renderização.
- O catálogo base mantém traduções específicas para `en`, `es` e `fr`; o catálogo estendido fornece traduções prioritárias em `ru`, `de` e `hi`. Chaves estendidas ausentes usam inglês como fallback para evitar texto português inesperado; ao adicionar uma tela, completar as traduções nos sete locales.
- Preferências e progressos de interface não devem depender da reconstrução do tabuleiro.

## Requisitos de Segurança e Operação

- Segredos ficam em variáveis de ambiente; nunca adicionar `.env` ao Git.
- Usar parâmetros SQL e escapar conteúdo não confiável inserido em HTML.
- Aplicar limites de tamanho, validações de domínio e rate limiting em endpoints sujeitos a abuso.
- Render usa `pip install -r requirements.txt` e `gunicorn --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT xadrez:app`.
- O `render.yaml` usa plano `free`, runtime Docker e SQLite efêmero. O Dockerfile instala Stockfish em `/usr/games/stockfish`, cria `/usr/local/bin/stockfish` como caminho executável estável e testa o handshake UCI; o serviço fornece `/usr/local/bin/stockfish` em `STOCKFISH_PATH`. O resolver retorna o caminho absoluto canonizado e procura os locais padrão caso a variável esteja obsoleta.
- Com `APP_ENV=production`, startup exige `SECRET_KEY`, `DATABASE_PATH` absoluto em diretório existente/gravável e Stockfish executável. O app valida disponibilidade local, não consegue certificar que o diretório é persistente no provedor.
- Configure `STOCKFISH_PATH` para um binário Linux confiável ou disponibilize `stockfish` no `PATH`. O app não concede permissões de execução implicitamente. Busca UCI tem timeout, no máximo quatro processos simultâneos e cleanup que espera/termina/recolhe subprocessos.
- Mutações de partida adquirem `BEGIN IMMEDIATE` antes da leitura para serializar transições concorrentes. O lock de escrita do SQLite é global ao arquivo, então gravações de partidas diferentes também podem aguardar. Mantenha um único worker Gunicorn; aumentar threads não distribui locks entre hosts nem substitui armazenamento multiwriter.
- `cleanup_ephemeral_sessions()` remove entradas de fila sem heartbeat recente, entradas pareadas sem partida ativa e presença com mais de sete dias. É acionada pelos fluxos de presença e fila; não é um scheduler nem substitui limpeza operacional regular.
- Antes do deploy: validar diagnósticos, fluxos críticos em ambiente local, `git diff --check`, branch remota e alterações staged.

## Manutenção

Manter UI e regras de negócio em camadas distintas. Rotas HTTP devem coordenar validação e persistência; cálculos de xadrez ficam em `core/engine.py` ou nos helpers de domínio. Alterações de esquema precisam preservar dados existentes. Atualizar `PROGRESSO.md` ao concluir e validar cada etapa.