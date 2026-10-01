# Capybara Chess: execução e publicação

## Teste no computador

1. Crie/ative um ambiente virtual e instale `requirements.txt`.
2. Copie `.env.example` para `.env` e gere `SECRET_KEY` com `openssl rand -hex 32`.
3. Para o login Google local, crie um OAuth Client do tipo Web no Google Cloud Console e cadastre `http://127.0.0.1:5000/auth/google/callback` como URI de redirecionamento.
4. Defina `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` no ambiente; mantenha `COOKIE_SECURE=false` em HTTP local.
5. Inicie `python xadrez.py` ou `gunicorn --workers 1 --threads 4 --bind 0.0.0.0:5000 xadrez:app` e abra `http://127.0.0.1:5000`.

O servidor local fica disponível na rede local pela porta 5000, mas isso não o torna acessível pela internet quando o computador está desligado. Não exponha a porta diretamente à internet.

## Login Google

No Google Cloud Console, configure a tela de consentimento OAuth e crie uma credencial de aplicativo Web. Cadastre os domínios e callbacks exatos do ambiente publicado, por exemplo `https://SEU-DOMINIO/auth/google/callback`. Configure `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` e uma chave aleatória estável `SECRET_KEY` como variáveis secretas do host. Em HTTPS, use `COOKIE_SECURE=true`.

O botão Google só aparece quando as duas credenciais estão definidas. Jogadores atuais devem entrar com nick e senha e, em Configurações > Perfil, vincular a conta Google para manter o mesmo nick, rating, moedas e demais dados. Um primeiro login Google sem sessão cria uma nova conta; ele não associa automaticamente contas antigas pelo e-mail.

Nunca publique `.env`, Client Secret ou `SECRET_KEY`. Se uma chave real for exposta, revogue-a no Google Cloud Console e gere outra.

## Hospedagem gratuita

O app agora tem um entry point WSGI (`xadrez:app`), `Procfile` e um exemplo para PythonAnywhere em `deployment/pythonanywhere_wsgi.py`. PythonAnywhere oferece um plano gratuito com WSGI e arquivos no diretório do usuário; confirme os limites vigentes e se o plano permite os endpoints OAuth do Google e executar o binário Stockfish (`/usr/games/stockfish` ou `stockfish` no `PATH`). O pacote Python `stockfish` sozinho não instala o executável da engine.

Passos para publicar esse exemplo:

1. Crie a conta gratuita no PythonAnywhere e um web app Flask; escolha uma versão Python suportada pelo host.
2. Envie o projeto para um diretório privado da sua conta e instale `requirements.txt` em um virtualenv. No arquivo WSGI criado pelo host, use o conteúdo de `deployment/pythonanywhere_wsgi.py` e ajuste `CAPYBARA_PROJECT_ROOT` para `/home/SEU-USUARIO/capybara-chess`.
3. No arquivo WSGI do host, defina `APP_ENV=production`, uma `SECRET_KEY` aleatória estável, `COOKIE_SECURE=true`, `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET`. Esse arquivo fica no host, fora do workspace e do repositório; não publique valores reais.
4. No Google Cloud Console, cadastre `https://SEU-USUARIO.pythonanywhere.com/auth/google/callback` como URI autorizada. Recarregue o web app e teste `/health`, cadastro e login.
5. Confira se a engine Stockfish está disponível. Se não estiver, o site e as contas podem abrir, mas as partidas contra bots não funcionarão nesse host. Faça backup de `capybara.db` antes de trocar código ou configuração.

O Google Cloud pode exigir configuração de consentimento, domínios autorizados e, para usuários fora da lista de teste, publicação/verificação do aplicativo. Esses passos dependem da conta Google do proprietário e não podem ser concluídos neste workspace.

A conta e o jogo usam SQLite. Em hospedagem, configure `DATABASE_PATH` para uma pasta persistente e protegida do host, fora da pasta pública. Não use filesystem efêmero: uma implantação ou reinicialização pode apagar contas e progresso. Faça backup regular de `capybara.db`. Os planos gratuitos variam e podem não oferecer disco persistente ou engine Stockfish; nesse caso, não há como garantir simultaneamente custo zero, dados duráveis e partidas com bot nesse provedor. Não publique o app até confirmar esses três pontos.

As contas Google são a identidade de login, mas os dados do jogo continuam no banco do servidor. Vincular Google não substitui backup e não transfere automaticamente o SQLite do computador para a hospedagem. Para migrar dados locais, faça uma cópia do banco e importe-a de forma segura antes de apontar os jogadores ao novo domínio.

## Instalação no celular e computador

O manifesto e o service worker tornam a interface instalável em navegadores compatíveis. Publique primeiro em HTTPS e abra o domínio no Chrome/Edge; use a opção de instalar aplicativo. No iPhone/iPad, abra no Safari e use Compartilhar > Adicionar à Tela de Início. A PWA guarda o app shell e recursos já carregados, mas login, ranking, mensagens e Stockfish continuam precisando do servidor; cache offline não transforma essas APIs em um servidor independente.
