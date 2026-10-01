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

SQLite é o armazenamento atual. `DATABASE_PATH` seleciona o arquivo; em produção no Render, os dados persistentes exigem um disco persistente montado e essa variável apontando para o disco. O serviço definido em `render.yaml` usa Gunicorn, um worker e quatro threads. As migrações em `init_db()` devem ser aditivas e manter valores padrão para contas antigas.

A sessão Flask identifica o usuário autenticado. Endpoints de escrita devem derivar a identidade da sessão, validar os dados recebidos e usar consultas parametrizadas. Não confiar em nomes de usuário enviados pelo cliente para autorizar ações privadas.

## Fluxos Principais

### Conta e perfil

1. O cliente envia cadastro ou login para o blueprint de autenticação.
2. O servidor valida a conta, cria/consulta o perfil e responde com dados usados pelo lobby.
3. O perfil permite nome de exibição, bio de até 30 caracteres, avatar e preferências.

### Partidas

1. O jogador escolhe modo, cor, ritmo e adversário.
2. O servidor cria a partida e fornece FEN, participantes e relógios.
3. O cliente atualiza o tabuleiro de forma responsiva e envia lances UCI.
4. O servidor valida regras e relógios, atualiza a posição e retorna o estado autoritativo.
5. A análise posterior consulta a engine sem alterar o resultado da partida.

### Social

Ranking abre o perfil público de um jogador. O perfil informa bio e partidas concluídas. Pedidos de amizade são persistidos, expostos em notificações e podem ser aceitos ou recusados; conversas são permitidas após aceite.

### Cosméticos

Compras são validadas no servidor contra o catálogo. Inventário e item equipado persistem no perfil. Skins de peça alteram a apresentação dos SVGs no cliente sem substituir os assets locais.

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
- Antes do deploy: validar diagnósticos, fluxos críticos em ambiente local, `git diff --check`, branch remota e alterações staged.

## Manutenção

Manter UI e regras de negócio em camadas distintas. Rotas HTTP devem coordenar validação e persistência; cálculos de xadrez ficam em `core/engine.py` ou nos helpers de domínio. Alterações de esquema precisam preservar dados existentes. Atualizar `PROGRESSO.md` ao concluir e validar cada etapa.