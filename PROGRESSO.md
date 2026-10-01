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

### Fase 1: interface e estado

- [x] Preservar o passo atual do Guia da Capivara ao navegar para outra seção e reabri-lo.
- [x] Exibir conquistas bloqueadas em cinzento e desbloqueadas com a cor normal.

### Fase 2: lógica do jogo e IA

- [x] Corrigir a avaliação da máquina e a classificação dos lances; limitar a reflexão do bot a 4 segundos e jogar instantaneamente com 10 segundos ou menos no relógio.
- [x] Expandir o tutorial para cobrir as funcionalidades restantes do jogo.

### Fase 3: funcionalidades sociais e backend

- [x] Permitir consultar perfil, histórico e bio de jogadores pelo ranking; implementar envio, recebimento, aceitação e rejeição de pedidos de amizade com notificações.

### Pendência anterior fora desta sequência

- [ ] Remover a restrição offline das missões e disponibilizá-las nos modos relevantes.

## Polimento final

- [x] Internacionalização: removida a definição duplicada de `setLanguage`, eliminadas chaves duplicadas do catálogo e ampliadas traduções de autenticação, configurações, loja, tabuleiro, clubes, ranking, promoção e desafio nos sete locales. Validado no navegador; o catálogo não tem chaves repetidas. Strings sem tradução específica em `ru`, `de` e `hi` usam fallback em inglês. Francês validado em Configurações, loja, tutorial e conquistas, inclusive descrições e estados acessíveis.
- [x] Acessibilidade: paleta de alto contraste aplicada também ao tabuleiro de análise; cores computadas validadas (`#f0e442` e `#0072b2`).
- [x] Música: removido o timer de quatro segundos do botão de teste de trilha. Validado que a sequência continua ativa ao abrir Configurações.
- [x] Tabuleiro: interação de clique por origem/destino validada com `e2e4`. O suporte por toque existente foi preservado; o navegador de teste não permite habilitar `hasTouch`, então não foi possível fazer uma simulação touchscreen nativa nesta rodada.
- [x] Animação: `moveSpeed` centralizado em 160 ms e respeita `prefers-reduced-motion`; validação confirmou 160 ms passados ao jQuery do chessboard.js.
- [x] Documentação: criado `REQUISITOS.md` com arquitetura, fluxos, operação no Render e orientações de manutenção. Adicionados comentários curtos nas rotinas centrais de jogo, tradução, áudio e navegação.