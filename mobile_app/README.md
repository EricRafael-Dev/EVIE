# Evie Mobile — Aplicativo Nativo Android (MVP)

Aplicativo Android **100% nativo em Kotlin** (sem WebView, sem wrappers web), construído no padrão de aplicativos modernos (como o app do Google Gemini / Assistant).

---

## 🚀 Como funciona a Conectividade (Tailscale)

- **Computador (Host):** `rafael` no IP `100.73.5.37:8000`
- **Celular (Cliente):** `poco-x7` no IP `100.83.118.62`
- **Comunicação:** Direta, criptografada ponto-a-ponto via WireGuard (Tailscale), sem passar por navegadores nem abrir portas públicas.

---

## 🧩 Modularidade (Adicionar / Remover Dispositivos)

Nenhum IP ou aparelho está fixado ("engessado") no código:

1. **No Computador (`config/devices.json`):**
   Para autorizar ou nomear um novo aparelho (ex: tablet, outro celular), basta adicionar ao registro:
   ```json
   {
     "name": "poco-x7",
     "tailscale_ip": "100.83.118.62",
     "os": "Android 16",
     "enabled": true,
     "role": "mobile_client"
   }
   ```
   A Evie detecta o novo dispositivo em tempo real.

2. **No Aplicativo Celular:**
   Ao tocar no ícone de engrenagem no topo do aplicativo, você pode apontar para qualquer IP/Host Tailscale sem precisar recompilar o app.

---

## 🛠️ Como Gerar o APK

### Opção 1: Via Android Studio (Recomendado)
1. Abra o **Android Studio**.
2. Clique em **File > Open** e selecione a pasta `mobile_app`.
3. Vá no menu **Build > Build Bundle(s) / APK(s) > Build APK(s)**.
4. O APK gerado estará em `app/build/outputs/apk/debug/app-debug.apk`.
5. Transfira para o seu Poco X7 e instale!

### Opção 2: Linha de comando / Script
Execute o arquivo `COMPILAR_APK.bat` ou pelo terminal:
```bash
./gradlew assembleDebug
```
