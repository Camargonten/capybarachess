# Progresso do Capybara Chess

## Concluído e validado

- Toque em dispositivos móveis (`tap-to-move`), correção dos botões de ranking e separação do nome de perfil (`display_name`), conforme estado informado pelo usuário. Não reprocessar.
- Música de fundo: abrir Configurações inicia ou mantém a trilha quando habilitada e fora de uma partida. Validado no navegador: timer ativo em Configurações e bloqueado durante partida.
- Modo daltônico: aplicada paleta azul/amarelo de alto contraste e restaurada a preferência salva ao autenticar. Idioma: textos estáticos são reaplicados ao trocar idioma com a tela de partida já montada. Validado no navegador por cores computadas e atualização imediata do botão de lance.
- Skins de peças: adicionada categoria com imagens SVG na grade e prévia, filtros visuais aplicados também aos tabuleiros, e compra/equipamento persistidos no perfil. Validado no navegador (3 imagens carregadas e filtros aplicados) e por teste HTTP de compra, equipamento e novo login.
- Avaliação e IA: avaliação do Stockfish fixada na perspectiva das brancas, classificação compara a posição antes/depois pelo lado que moveu e melhor lance vem da posição anterior. Bot busca por até 4 s e usa busca mínima quando seu próprio relógio está em 10 s ou menos. Validado para ambos os lados com engine simulada e busca legal real em 4,54 s.
- Guia da Capivara: expandido para dez etapas sobre as áreas existentes, com conteúdo e navegação em sete idiomas. Validado em todos os idiomas e passos; adicionados destinos diretos e fallback de idioma para os campos de busca/conversa.
- Perfis e amizades: perfil/histórico público acessível pelo ranking, bio persistente limitada a 30 caracteres, pedidos de amizade com caixa de notificações e polling, aceite/recusa e autenticação por sessão. Validado em navegador e por teste HTTP com banco temporário.

## Pendências, na ordem solicitada

### Fase 1: loja e perfil

- [x] Gerar URLs de peças e avatares com `url_for('static', ...)`, respeitando prefixos de montagem como `SCRIPT_NAME`.
- [x] Cobrar zero moedas na primeira alteração de nome e 100 nas seguintes, com validação e débito atômico do saldo.
- [x] Validar caminhos com prefixo Flask e fluxo de nome em SQLite temporário.

### Fase 1: interface e estado

- [x] Preservar o passo atual do Guia da Capivara ao navegar para outra seção e reabri-lo.
- [x] Exibir conquistas bloqueadas em cinzento e desbloqueadas com a cor normal.

### Fase 2: lógica do jogo e IA

- [x] Corrigir a avaliação da máquina e a classificação dos lances; limitar a reflexão do bot a 4 segundos e jogar instantaneamente com 10 segundos ou menos no relógio.
- [x] Expandir o tutorial para cobrir as funcionalidades restantes do jogo.

### Fase 3: funcionalidades sociais e backend

- [x] Permitir consultar perfil, histórico e bio de jogadores pelo ranking; implementar envio, recebimento, aceitação e rejeição de pedidos de amizade com notificações.

### Pendência anterior fora desta sequência

- [x] Corrigir o carregamento de missões, substituir objetivos inalcançáveis por 30 missões offline variadas e automatizar progresso/resgate.

### Fase 2: missões e economia

- [x] Catalogar 30 missões em três dificuldades, com progresso a partir de partidas contra bots, incluindo vitórias por cor/ritmo, xeque-mate, roque, promoção, capturas e volume de partidas.
- [x] Atualizar progresso no encerramento normal, por desistência, timeout e empate aceito pelo bot; retornar conclusões recentes para feedback imediato no cliente.
- [x] Tornar resgates transacionais e de uso único, com saldo atualizado no perfil.
- [x] Reduzir ganhos repetíveis contra bots para 3/5/8 moedas por vitória em Bullet/Blitz/Rápida e 1/1/2 por empate; recompensas de missão variam de 8 a 50 moedas.
- [x] Validar catálogo/listagem/progresso/resgate idempotente, desistência, timeout e empate aceito em SQLite isolado; diagnósticos do editor sem erros.

### Fase 4: calibração, tutorial e modos de partida

- [x] Exigir calibração server-side antes de matchmaking clássico/rankeado ou entrada em partidas PvP ranqueadas; somente os dois primeiros resultados contra bots oficiais 1–5 alteram o rating FIDE, inclusive empate aceito.
- [x] Exibir progresso da calibração no lobby e limitar a seleção inicial aos cinco bots elegíveis.
- [x] Fazer o tutorial obrigatório acompanhar as visitas por etapa/seção, bloquear navegação lateral e oferecer retorno ao guia; “Pular tutorial” conclui e libera explicitamente.
- [x] Criar fila PvP ranqueada persistida em SQLite, pareando pelo rating e ritmo com faixa de busca crescente, mais consulta de estado e cancelamento.
- [x] Impedir que uma partida casual ou contra bot ativa seja confundida com um pareamento ranqueado.
- [x] Ligar o modo Clássico ao catálogo de bots calibrados pelo rating atual; atualizar o rating clássico ao fim da partida sem alterar o rating FIDE.
- [x] Desativar o endpoint antigo que aceitava resultado clássico enviado pelo cliente.
- [x] Validar gates, pareamento, seleção de bot, rating clássico, conflito com partidas casuais e migrações em SQLite temporário; diagnósticos do editor sem erros.

### Fase 5: força e reflexão dos bots

- [x] Mapear ratings para 16 tiers Stockfish de 500 a 3000 Elo, com perfil de Skill Level para os seis tiers abaixo da faixa UCI e limitação Elo para os demais.
- [x] Aumentar o tempo de busca por tier de 300 ms a 3000 ms; usar 1 ms somente quando o relógio autoritativo do bot indicar 10 segundos ou menos.
- [x] Remover a escolha aleatória em falha do motor e retornar erro explícito; limitar ratings recebidos ao intervalo dos tiers.
- [x] Exibir o tier na configuração e na partida, preservando a seleção customizada de força.
- [x] Validar todos os perfis com motor simulado, tiers de fronteira com Stockfish 17 real e nível 16 normal/rápido com lances legais.

### Publicação no Render: configurada para teste online

- [x] Mantido plano `free` com SQLite em `DATABASE_PATH=/tmp/capybara.db`; banco, fila e estado social são efêmeros e podem se perder em reinicializações/deploys.
- [x] Alterado o serviço para runtime Docker; o `Dockerfile` instala a dependência Debian Stockfish, aplica modo `755` em `/usr/games/stockfish`, configura o caminho estável `/usr/local/bin/stockfish` e valida handshake UCI durante o build.
- [x] `render.yaml` configura `STOCKFISH_PATH`, `DATABASE_PATH`, healthcheck `/health` e Gunicorn com um worker/quatro threads, sem disco pago.

### Auditoria de concorrência e espectador

- [x] Duas partidas PvP de pares diferentes receberam lances simultâneos sem compartilhar FEN ou histórico.
- [x] Dois lances concorrentes no mesmo turno gravaram apenas um movimento; o segundo pedido recebeu 403 após revalidar turno.
- [x] Adicionada a lista de partidas ativas de amigos e observação em polling somente leitura; espectadores autenticados veem tabuleiro/notação ao vivo e não podem enviar lances, desistir ou reivindicar timeout.
- [x] Validado HTTP 200 para amigo/participante, HTTP 403 para estranho/timeout de espectador e HTTP 401/403 para tentativas de falsificar identidade; timeout do observador é read-only. Teste visual confirmou atualização de `e4`/`d5` no tabuleiro e controles de jogo ocultos.

### Operação, segurança e validação final

- [x] Produção falha explicitamente sem `SECRET_KEY`, `DATABASE_PATH` absoluto em diretório existente/gravável ou Stockfish executável; caminhos não executáveis não recebem chmod implícito.
- [x] Stockfish usa `SimpleEngine`, até quatro slots concorrentes, timeout no handshake/busca e encerramento/recolhimento do subprocesso. Validado com Stockfish real e handshake UCI inválido com timeout.
- [x] Mutação de partida (entrada, lance, desistência, empate, takeback e timeout) obtém `BEGIN IMMEDIATE` antes de consultar o estado. Duas requisições de lance concorrentes resultaram em uma única gravação (200/403).
- [x] Limpeza de filas sem heartbeat, partidas pareadas já encerradas e presenças com mais de sete dias validada em SQLite temporário.
- [x] Validadores de FEN, UCI, username e inteiros rejeitam payloads com tipo, formato, whitespace/controlos ou limites inválidos.
- [ ] Validar o build e o healthcheck no Render após o push; os dados permanecem efêmeros por decisão para este teste online.

## Polimento final

- [x] Internacionalização: removida a definição duplicada de `setLanguage`, eliminadas chaves duplicadas do catálogo e ampliadas traduções de autenticação, configurações, loja, tabuleiro, clubes, ranking, promoção e desafio nos sete locales. Validado no navegador; o catálogo não tem chaves repetidas. Strings sem tradução específica em `ru`, `de` e `hi` usam fallback em inglês. Francês validado em Configurações, loja, tutorial e conquistas, inclusive descrições e estados acessíveis.
- [x] Acessibilidade: paleta de alto contraste aplicada também ao tabuleiro de análise; cores computadas validadas (`#f0e442` e `#0072b2`).
- [x] Música: removido o timer de quatro segundos do botão de teste de trilha. Validado que a sequência continua ativa ao abrir Configurações.
- [x] Tabuleiro: interação de clique por origem/destino validada com `e2e4`. O suporte por toque existente foi preservado; o navegador de teste não permite habilitar `hasTouch`, então não foi possível fazer uma simulação touchscreen nativa nesta rodada.
- [x] Animação: `moveSpeed` centralizado em 160 ms e respeita `prefers-reduced-motion`; validação confirmou 160 ms passados ao jQuery do chessboard.js.
- [x] Documentação: criado `REQUISITOS.md` com arquitetura, fluxos, operação no Render e orientações de manutenção. Adicionados comentários curtos nas rotinas centrais de jogo, tradução, áudio e navegação.
- [x] Estrutura do Guia: renomeada a pasta vazia para `capybara-guide` e adicionada nota de escopo. Busca global não encontrou imports, assets ou caminhos runtime para migrar; a feature continua implementada no template principal.
