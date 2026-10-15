# 🚀 JARVIS Brave Controller — Extensão para Navegador Brave

Extensão Manifest V3 desenvolvida sob medida para o navegador **Brave** (e compatível com Google Chrome / Edge). Ela permite controle total de abas, extração inteligente de artigos, tabelas e metadados, captura de telas em alta qualidade e comunicação em tempo real via WebSocket com o assistente JARVIS (Python).

---

## 📦 Como Instalar no Brave (Passo a Passo)

1. Abra o navegador **Brave**.
2. Na barra de endereços, digite:
   ```text
   brave://extensions
   ```
3. No canto superior direito da página, **ative a chave "Modo do desenvolvedor"** (Developer mode).
4. No canto superior esquerdo, clique no botão **"Carregar sem compactação"** (Load unpacked).
5. Selecione a pasta da extensão:
   ```text
   c:\Users\Rafael\OneDrive\Documentos\Mark-LV-main\Mark-LV-main\brave_extension
   ```
6. Pronto! O ícone com o núcleo ciano do JARVIS aparecerá na barra de ferramentas do seu Brave.
   > **Dica:** Clique no ícone de "quebra-cabeça" na barra do Brave e fixe (pin) a extensão para fácil acesso!

---

## ⚡ Funcionalidades

### 1. 📑 Gerenciador de Guias (Tabs Manager)
- **Alternar Guias:** Clique em qualquer guia na lista para focar e alternar para ela instantaneamente.
- **Fechar Guias:** Botão de fechar individual `✕`.
- **Limpeza de Duplicadas:** Botão `🧹 Duplicadas` detecta e fecha abas repetidas com um clique.
- **Fechar por Domínio:** Botão `🚫 Deste Domínio` fecha todas as abas abertas do site ativo.
- **Fixar e Silenciar:** Ícones de fixação `📌` e áudio `🔊/🔇` diretamente no card da guia.
- **Barra de Comandos Rápidos:**
  - Digite o nome de um site para filtrar instantaneamente.
  - Digite `:dup` para fechar duplicadas.
  - Digite `fechar youtube` para fechar todas as abas do YouTube.
  - Pressione `Enter` para alternar direto para a primeira guia filtrada.

### 2. 📄 Extração Inteligente de Conteúdo
- **Artigo Limpo (Markdown):** Remove propagandas, menus, popups e anúncios, extraindo o conteúdo principal da página formatado em Markdown pronto para IA.
- **Metadados & SEO:** Extrai Título, Descrição, Tags OpenGraph, Autor, Favicon e Palavras-chave em JSON.
- **Todos os Links:** Lista completa de URLs e textos âncora da página.
- **Tabelas Estruturadas:** Detecta todas as tabelas HTML e converte para JSON e Markdown.
- **Formulários:** Mapeia todos os campos de formulários da página e valores atuais.
- **Texto Selecionado:** Captura o trecho atualmente destacado pelo cursor do mouse.
- **Exportação:** Botões `📋 Copiar` e `💾 Salvar` (.md, .json, .txt).

### 3. 📸 Captura de Tela (Screenshot)
- Captura em alta definição da aba ativa.
- Pré-visualização instantânea no painel.
- Botões de `Copiar Imagem` para a área de transferência ou `Baixar PNG`.

### 4. 🔗 Conexão em Tempo Real com o JARVIS (Python WebSocket)
- A extensão se conecta automaticamente ao servidor local do JARVIS em `ws://127.0.0.1:8765`.
- Se o JARVIS estiver rodando, a extensão exibe o indicador verde `JARVIS CONECTADO`.
- Permite que comandos de voz ou automações no Python controlem o navegador em segundo plano:
  ```python
  from actions.browser_extension_server import brave_controller

  # Exemplos no Python:
  await brave_controller.list_tabs()
  await brave_controller.switch_tab(query="github")
  await brave_controller.close_tabs(duplicates_only=True)
  content = await brave_controller.extract_content(mode="article")
  screenshot_bytes = await brave_controller.capture_screenshot(save_path="screenshot.png")
  ```

---

## 🧪 Testando a Conexão com o Python

Para testar a ponte Python imediatamente:

1. No terminal, execute:
   ```powershell
   python actions/browser_extension_server.py
   ```
2. Abra o Brave com a extensão instalada.
3. O terminal mostrará:
   ```text
   ✅ Extensão conectada com sucesso!
   Total de guias abertas no Brave: X
   ```
