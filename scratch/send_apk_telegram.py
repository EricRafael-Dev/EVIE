import requests
import sys

TOKEN = "8631424288:AAGICyxZ9wZ9VuSI4Cs7AT-LpLeh_O6Agig"
CHAT_ID = "1409623681"
APK_PATH = r"c:\Users\Rafael\OneDrive\Documentos\Mark-LV-main\Mark-LV-main\mobile_app\Evie-poco-x7.apk"

caption = "🚀 Evie Assistant - Resolução 1080p Ultrawide + Correção de Pinça"

full_changelog = (
    "🖥️ *Evie Assistant - Resolução 1080p e Correção de Pinça*\n\n"
    "✨ *O que foi corrigido nesta build:*\n\n"
    "1. 💎 *Resolução 1080p Real no Ultrawide*: A largura mínima de captura agora é de 2560px (proporção 21:9 em 1080p de altura) com qualidade JPEG calibrada para 82 sem redução artificial de compressão. Fontes, código e terminais agora aparecem com máxima nitidez mesmo ao aproximar o zoom.\n\n"
    "2. 🛡️ *Fim do Bug de Renderização na Pinça*: O sistema de zoom foi totalmente reconstruído para usar *Matrix GPU Direta* (`imageMatrix`). Não há mais divisão da tela ou saltos para direções opostas durante o gesto de pinça.\n\n"
    "3. 🧭 *Pan Suave e Travamento nas Bordas*: Ao estar com zoom, o arrasto com 2 dedos (ou 1 dedo no modo PAN) respeita estritamente os limites da tela sem nunca sair do enquadramento.\n\n"
    "4. 🎯 *Mapeamento Exato de Cliques*: Mapeamento por matriz inversa em tempo real, permitindo tocar ou clicar com precisão de pixel em qualquer parte da tela com zoom."
)

print("Enviando mensagem descritiva para o Telegram...")
r_msg = requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    data={"chat_id": CHAT_ID, "text": full_changelog, "parse_mode": "Markdown"},
    timeout=30
)
print("Msg status:", r_msg.status_code)

print(f"Enviando {APK_PATH} para o Telegram...")
url = f"https://api.telegram.org/bot{TOKEN}/sendDocument"

with open(APK_PATH, "rb") as f:
    resp = requests.post(
        url,
        data={"chat_id": CHAT_ID, "caption": caption},
        files={"document": ("Evie-poco-x7.apk", f, "application/vnd.android.package-archive")},
        timeout=180
    )

print("Resposta:", resp.status_code, resp.text[:200])
if resp.status_code == 200:
    print("Sucesso! APK entregue no Telegram com sucesso.")
else:
    print("Falha no envio do APK.")
    sys.exit(1)
