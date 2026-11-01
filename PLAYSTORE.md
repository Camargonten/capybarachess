# Capybara Chess na Google Play Store

O jogo já está preparado como **PWA** e pode ser empacotado como **Trusted Web Activity (TWA)**: um app Android que abre o seu site em tela cheia (Chrome), sem reescrever nada. Este guia lista o que já está pronto e o que só você pode fazer (conta, assinatura e envio).

## 1. O que já está pronto no código

| Item | Onde |
|---|---|
| Manifest PWA completo (nome, ícones 48–512, ícone *maskable*, `standalone`, retrato, categorias) | `static/manifest.webmanifest` |
| Ícones PNG (any + maskable) | `static/icons/` |
| Ícone da loja 512×512 e gráfico de recursos 1024×500 | `static/store/` |
| Service worker (app shell em cache, versão `capybara-shell-v4`) | `static/sw.js` |
| Digital Asset Links (liga o site ao app) | rota `/.well-known/assetlinks.json` (variáveis `ANDROID_PACKAGE_NAME` e `ANDROID_SHA256_CERT_FINGERPRINTS`) |
| Política de Privacidade, Termos e página "Excluir conta" (URLs públicas exigidas) | `/privacidade`, `/termos`, `/excluir-conta` |
| Exclusão de conta dentro do app (exigência da Play) | Configurações → Suporte → **Excluir minha conta** (`POST /account/delete`) |
| Config do empacotador (Bubblewrap) | `playstore/twa-manifest.json` |
| Dados persistentes (PostgreSQL) para o servidor gratuito não apagar tudo | `DEPLOY.md` |

Sem anúncios, sem compras com dinheiro real, sem permissões especiais (câmera, localização etc.).

## 2. Antes de tudo: servidor em HTTPS com banco persistente

1. Publique no Render (ou outro) com **HTTPS** e `DATABASE_URL` apontando para um PostgreSQL gratuito (veja `DEPLOY.md`).
2. No Google Cloud Console (login Google), cadastre o callback de produção `https://SEU-DOMINIO/auth/google/callback` e **publique** a tela de consentimento (status "Em produção"), senão só usuários de teste conseguem entrar.
3. Abra `https://SEU-DOMINIO/health` e `https://SEU-DOMINIO/privacidade` para conferir.

> O Render gratuito "dorme" após inatividade e a primeira abertura pode demorar. Para a loja, considere um plano sempre ligado ou aceite essa limitação.

## 3. Gerar o app Android (AAB)

Precisa de Node.js e JDK 17 (o Bubblewrap pode baixar o JDK/SDK sozinho).

```bash
npm i -g @bubblewrap/cli
mkdir capybara-android && cd capybara-android
# Edite playstore/twa-manifest.json: troque SEU-APP.onrender.com pelo seu domínio e confira packageId
cp ../playstore/twa-manifest.json .
bubblewrap init --manifest=https://SEU-DOMINIO/static/manifest.webmanifest   # ou use o twa-manifest.json
bubblewrap build        # gera app-release-bundle.aab e a chave capybara-upload.keystore
```

- **Guarde o `.keystore` e a senha em lugar seguro (e com backup).** Sem ele você não consegue atualizar o app.
- O `packageId` (`br.com.capybarachess.app`) não pode mais mudar depois de publicado.

## 4. Play Console (única etapa 100% manual)

1. Crie a conta de desenvolvedor (taxa única de US$ 25) e o app (Jogo, gratuito).
2. **Play App Signing** (recomendado): ao enviar o primeiro `.aab`, o Google assina o app. Em *Configurações → Integridade do app*, copie a **impressão digital SHA-256 do certificado de assinatura do app**.
3. No servidor defina:
   ```
   ANDROID_PACKAGE_NAME=br.com.capybarachess.app
   ANDROID_SHA256_CERT_FINGERPRINTS=AA:BB:...   # a da Play; pode listar também a da chave de upload, separadas por vírgula
   ```
   Confirme em `https://SEU-DOMINIO/.well-known/assetlinks.json`. Sem isso o app abre com a barra de endereço do Chrome (não é tela cheia).
4. **Ficha da loja** (textos sugeridos abaixo), ícone `static/store/play-store-icon-512.png`, gráfico `static/store/feature-graphic-1024x500.png` e **capturas de tela** (mín. 2, tiradas de um celular real em 1080×1920 ou maior — não incluí capturas porque as do ambiente de desenvolvimento têm baixa resolução).
5. **URLs**: Política de Privacidade `https://SEU-DOMINIO/privacidade`; exclusão de conta `https://SEU-DOMINIO/excluir-conta`.
6. **Formulários** (responda conforme a sua realidade; pontos de partida):
   - *Anúncios:* não. *Compras no app:* não.
   - *Classificação de conteúdo (IARC):* jogo de tabuleiro, sem violência; há **interação entre usuários** (mensagens, clubes, nomes e fotos de perfil).
   - *Público-alvo:* 13 anos ou mais (a política diz que não é direcionado a menores de 13).
   - *Segurança dos dados:* coleta **nome de usuário, e-mail (opcional, via Google), ID de usuário, foto de perfil (opcional), mensagens e atividade no app (partidas)**; dados **criptografados em trânsito**; o usuário **pode solicitar exclusão** (link acima); **não** compartilha com terceiros para publicidade.
7. **Teste fechado:** contas pessoais novas costumam precisar de um teste fechado com testadores por ~14 dias antes de publicar em produção. Confira a regra vigente no Play Console.

### Textos sugeridos (pt-BR)

**Título:** Capybara Chess — Xadrez
**Descrição curta (80):** Xadrez com bots, amigos, ranking e missões. Jogue grátis!
**Descrição completa:**
> Jogue xadrez com a capivara mais estratégica do mundo! Enfrente bots de vários níveis (do iniciante ao nível mestre), desafie amigos, entre no ranking online e no modo Bermuda, cumpra missões, junte Camarcoins e personalize seu perfil com molduras, capas e peças.
> • Bots para todos os níveis, inclusive desafios especiais
> • Partidas online e revanche com inversão de cores
> • Premove e confirmação de lance para jogar do seu jeito
> • Clubes, amigos e presentes com animação
> • Calibração automática de rating
> • Português, English, Español, Français, Русский, Deutsch e हिन्दी
> Sem anúncios e sem compras com dinheiro real.

## 5. Checklist final

- [ ] `https://SEU-DOMINIO` abre, instala como PWA e passa no Lighthouse (PWA).
- [ ] `assetlinks.json` lista o pacote e o SHA-256 da Play.
- [ ] Login Google funciona no celular (abre no Chrome e volta ao app).
- [ ] Excluir conta funciona (teste com uma conta descartável).
- [ ] Política de Privacidade revisada por quem entende de LGPD (o texto incluído é um ponto de partida, não parecer jurídico).
- [ ] Capturas de tela reais enviadas.
