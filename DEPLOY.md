# Capybara Chess: execução e publicação

## Teste no computador

1. Crie/ative um ambiente virtual e instale `requirements.txt`.
2. Copie `.env.example` para `.env` e gere `SECRET_KEY` com `openssl rand -hex 32`.
3. Para o login Google local, crie um OAuth Client do tipo Web no Google Cloud Console e cadastre `http://127.0.0.1:5000/auth/google/callback` como URI de redirecionamento.
4. Defina `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` no ambiente; mantenha `COOKIE_SECURE=false` em HTTP local.
5. Inicie `python app.py` ou `gunicorn --workers 1 --threads 4 --bind 127.0.0.1:5000 app:app` e abra `http://127.0.0.1:5000`.

O comando local liga o servidor somente em `127.0.0.1:5000`, acessível neste computador. Não exponha a porta diretamente à internet; para uma demonstração na rede local, configure explicitamente um host apropriado e use uma rede confiável.

## Login Google

No Google Cloud Console, configure a tela de consentimento OAuth e crie uma credencial de aplicativo Web. Cadastre os domínios e callbacks exatos do ambiente publicado, por exemplo `https://SEU-DOMINIO/auth/google/callback`. Configure `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` e uma chave aleatória estável `SECRET_KEY` como variáveis secretas do host. Em HTTPS, use `COOKIE_SECURE=true`.

O botão Google só aparece quando as duas credenciais estão definidas. Jogadores atuais devem entrar com nick e senha e, em Configurações > Perfil, vincular a conta Google para manter o mesmo nick, rating, moedas e demais dados. Um primeiro login Google sem sessão cria uma nova conta; ele não associa automaticamente contas antigas pelo e-mail.

Nunca publique `.env`, Client Secret ou `SECRET_KEY`. Se uma chave real for exposta, revogue-a no Google Cloud Console e gere outra.

## Banco de dados persistente (PostgreSQL) — leia antes de publicar

Contêineres gratuitos (Render Free) **apagam arquivos locais** quando o serviço dorme ou reinicia. Por isso o app suporta PostgreSQL externo:

- Com `DATABASE_URL` definida, **todos** os dados (contas, ratings, partidas em andamento, clubes, presentes...) ficam no PostgreSQL e sobrevivem a reinícios.
- Sem `DATABASE_URL`, o app usa SQLite local (bom para desenvolver no computador).

Passo a passo (Neon, gratuito; Supabase funciona igual):

1. Crie o projeto em https://neon.tech e copie a *connection string* (`postgresql://usuario:senha@host/banco?sslmode=require`).
2. No Render: *Environment* → adicione `DATABASE_URL` com essa string (e `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`). A `SECRET_KEY` é gerada uma vez pelo `render.yaml` e permanece estável (mantém as sessões entre reinícios).
3. No primeiro start o app cria as tabelas sozinho.
4. Para levar os dados atuais do SQLite: no seu computador, `DATABASE_URL='postgresql://...' python3 tools/migrate_sqlite_to_postgres.py capybara.db`. O script não altera o arquivo SQLite e pode ser repetido.
5. Teste: `DATABASE_URL=... python3 tests/smoke_api.py` (use um banco descartável; ele cria contas `smoke_*`).

Como o progresso é preservado:

- **Servidor/banco:** nada fica só na RAM. Partidas em andamento estão na tabela `games`; o app grava um *heartbeat* a cada 15 s e, ao religar depois de uma pausa, **congela os relógios** das partidas ativas pelo tempo em que ficou desligado (`freeze_clocks_after_downtime`). Assim cada partida volta exatamente ao ponto em que o último jogador a deixou.
- **Navegador:** ao abrir o jogo (ou quando a internet volta) o app consulta `/game/active` e retoma a partida. Partidas contra bots oficiais/extras também são copiadas no `localStorage`; se o servidor perder os dados, `/game/restore` recria a partida (validada, sem alterar rating/moedas/missões/selos).
- **Limites:** o limitador de requisições e o bloqueio de login ficam em memória e zeram ao reiniciar (por segurança isso é aceitável). No plano gratuito do Neon o banco pode "acordar" em ~1 s na primeira consulta.

## Hospedagem gratuita

O app usa `app:app` como entry point WSGI profissional; `xadrez:app` continua disponível para compatibilidade, assim como o exemplo para PythonAnywhere em `deployment/pythonanywhere_wsgi.py`. PythonAnywhere oferece um plano gratuito com WSGI e arquivos no diretório do usuário; confirme os limites vigentes e se o plano permite os endpoints OAuth do Google e executar o binário Stockfish (`/usr/games/stockfish` ou `stockfish` no `PATH`). O pacote Python `stockfish` sozinho não instala o executável da engine. Consulte [ARCHITECTURE.md](./ARCHITECTURE.md) para orientação de manutenção.

Passos para publicar esse exemplo:

1. Crie a conta gratuita no PythonAnywhere e um web app Flask; escolha uma versão Python suportada pelo host.
2. Envie o projeto para um diretório privado da sua conta e instale `requirements.txt` em um virtualenv. No arquivo WSGI criado pelo host, use o conteúdo de `deployment/pythonanywhere_wsgi.py` e ajuste `CAPYBARA_PROJECT_ROOT` para `/home/SEU-USUARIO/capybara-chess`.
3. No arquivo WSGI do host, defina `APP_ENV=production`, uma `SECRET_KEY` aleatória estável, `COOKIE_SECURE=true`, `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET`. Esse arquivo fica no host, fora do workspace e do repositório; não publique valores reais.
4. No Google Cloud Console, cadastre `https://SEU-USUARIO.pythonanywhere.com/auth/google/callback` como URI autorizada. Recarregue o web app e teste `/health`, cadastro e login.
5. Confira se a engine Stockfish está disponível. Se não estiver, o site e as contas podem abrir, mas as partidas contra bots não funcionarão nesse host. Faça backup de `capybara.db` antes de trocar código ou configuração.

O Google Cloud pode exigir configuração de consentimento, domínios autorizados e, para usuários fora da lista de teste, publicação/verificação do aplicativo. Esses passos dependem da conta Google do proprietário e não podem ser concluídos neste workspace.

Sem `DATABASE_URL` o jogo usa SQLite (`DATABASE_PATH`); nesse modo o Render Free usa `/tmp/capybara.db`, que é apagado em reinícios. **Em produção configure `DATABASE_URL` (seção acima).** O serviço instala Stockfish por Docker e executa bots nesse plano.

### Verificações de produção

Com `APP_ENV=production`, a aplicação não inicia sem `SECRET_KEY`, `DATABASE_PATH` absoluto apontando para um diretório existente e gravável, e Stockfish executável. Configure `STOCKFISH_PATH` para o binário instalado pelo host ou garanta `stockfish` no `PATH`; o processo não altera permissões do arquivo. O pacote Python `stockfish` não substitui esse executável. A aplicação valida caminho e escrita, mas não detecta se o provedor preserva os dados entre deploys.

O Gunicorn usa um worker e quatro threads. As rotas mutáveis leem o estado sob `BEGIN IMMEDIATE`; como o lock de escrita do SQLite é global ao arquivo, gravações de partidas diferentes também podem aguardar entre si. Mantenha um worker enquanto SQLite for o banco compartilhado; locks locais não substituem um banco multiworker distribuído. O motor limita a quatro processos concorrentes, aplica timeout de UCI e encerra/recolhe o subprocesso após cada busca.

O blueprint `render.yaml` usa o plano `free` e a runtime Docker. O `Dockerfile` instala o pacote Debian Stockfish, inclui `/usr/games` no `PATH`, dá permissão de execução aos aliases `/usr/games/stockfish` e `/usr/bin/stockfish`, e cria `/usr/local/bin/stockfish`; o build valida esses caminhos e o handshake UCI. O backend procura primeiro o `STOCKFISH_PATH` configurado, depois `shutil.which('stockfish')`, `/usr/games/stockfish`, `/usr/bin/stockfish` e, por fim, `stockfish` no `PATH`. Falhas são registradas com traceback completo e a resposta HTTP ao jogador permanece genérica. `DATABASE_PATH` usa `/tmp/capybara.db`; nenhum disco pago é criado e os dados são efêmeros.

As contas Google são a identidade de login, mas os dados do jogo continuam no banco do servidor. Vincular Google não substitui backup e não transfere automaticamente o SQLite do computador para a hospedagem. Para migrar dados locais, faça uma cópia do banco e importe-a de forma segura antes de apontar os jogadores ao novo domínio.

## Instalação no celular e computador

O manifesto e o service worker tornam a interface instalável em navegadores compatíveis. Publique primeiro em HTTPS e abra o domínio no Chrome/Edge; use a opção de instalar aplicativo. No iPhone/iPad, abra no Safari e use Compartilhar > Adicionar à Tela de Início. A PWA guarda o app shell e recursos já carregados, mas login, ranking, mensagens e Stockfish continuam precisando do servidor; cache offline não transforma essas APIs em um servidor independente.
