# nao_speaker.py
import json
import time
import urllib.request
import qi

SERVER_URL = "http://192.168.16.76:5000/visualizador/cena_atual"
NAO_IP     = "169.254.193.121"
NAO_PORT   = 9559

# ============================================================
# ANIMAÇÕES DISPONÍVEIS NO NAO (behavior names nativos)
# Caminho: animations/Stand/Gestures/
# ============================================================
ANIM_BASE = "animations/Stand/Gestures/"

GESTOS = {
    # Saudação
    "bemvindo":   ANIM_BASE + "Hey_1",
    "tchau":      ANIM_BASE + "Salute_1",

    # Positivo
    "animado":    ANIM_BASE + "Enthusiastic_4",
    "concordar":  ANIM_BASE + "Yes_1",
    "otimo":      ANIM_BASE + "Enthusiastic_1",

    # Negativo
    "discordar":  ANIM_BASE + "No_1",
    "triste":     ANIM_BASE + "Desperate_1",

    # Pensamento
    "pensar":     ANIM_BASE + "Think_1",
    "curioso":    ANIM_BASE + "Thinking_1",
    "duvida":     ANIM_BASE + "Confused_1",

    # Explicação
    "explicar":   ANIM_BASE + "Explain_1",
    "apontar":    ANIM_BASE + "ShowSky_1",
    "contar":     ANIM_BASE + "CountOne_1",

    # Outros
    "surpresa":   ANIM_BASE + "Surprise_1",
    "neutro":     ANIM_BASE + "Neutral_1",
}

# ============================================================
# MAPEAMENTO PALAVRA → GESTO
# ============================================================
POSES = [
    (["bem-vindo", "olá", "oi", "chegamos", "início",
      "começa", "vamos começar", "iniciar"],                      "bemvindo"),

    (["incrível", "uau", "wow", "surpreendente", "inesperado",
      "fantástico", "espantoso", "extraordinário"],               "surpresa"),

    (["parabéns", "conseguiu", "excelente", "ótimo", "perfeito",
      "vitória", "sucesso", "resolveu", "funcionou", "conquista"], "animado"),

    (["triste", "falhou", "erro", "problema", "frustrado",
      "fracasso", "infelizmente", "pena"],                        "triste"),

    (["pensa", "imagine", "questão", "como", "decidir",
      "analisar", "calcular", "resolver", "será que",
      "o que acha", "reflita", "hmm"],                            "pensar"),

    (["explica", "veja", "observe", "note", "perceba",
      "então", "portanto", "assim", "ou seja", "significa",
      "representa", "demonstra", "mostra"],                       "explicar"),

    (["sim", "correto", "exato", "certamente", "claro",
      "concordo", "está certo", "isso mesmo"],                    "concordar"),

    (["não", "nunca", "jamais", "errado", "incorreto",
      "discordo", "negativo"],                                     "discordar"),

    (["curioso", "interessante", "que estranho", "por que",
      "fascinante", "intrigante", "misterioso"],                  "curioso"),

    (["aqui está", "olha", "apresento", "este é",
      "conheça", "atenção", "aqui temos"],                        "apontar"),

    (["primeiro", "segundo", "terceiro", "primeiramente",
      "além disso", "importante", "principais"],                  "contar"),
]

def escolher_gesto(texto):
    texto_lower = texto.lower()
    for palavras, gesto in POSES:
        for palavra in palavras:
            if palavra in texto_lower:
                return gesto
    return "neutro"

def limpar_texto(texto):
    if not texto:
        return ""
    import re
    t = texto.replace('"', '').replace('«', '').replace('»', '')
    t = re.sub(r'[—–]', ',', t)
    t = t.replace('...', '.')
    t = re.sub(r'[*_~`#]', '', t)
    t = re.sub(r'\s{2,}', ' ', t)
    return t.strip()

# ============================================================
# CONEXÃO
# ============================================================
print("Conectando ao NAO...")
try:
    app = qi.Application(["nao_speaker", "--qi-url", "tcp://{}:{}".format(NAO_IP, NAO_PORT)])
    app.start()
    session = app.session

    tts     = session.service("ALTextToSpeech")
    anim    = session.service("ALAnimatedSpeech")
    motion  = session.service("ALMotion")

    tts.setLanguage("Brazilian")

    # Modo: "contextual" = NAO escolhe gestos automáticos enquanto fala
    # Você pode trocar por "disabled" para usar só os gestos manuais
    config = {"bodyLanguageMode": "contextual"}

    print("Conectado ao NAO!")
except Exception as e:
    print("Erro ao conectar ao NAO: " + str(e))
    raise SystemExit

# ============================================================
# LOOP PRINCIPAL
# ============================================================
ultimo_texto = None
print("Monitorando servidor... (CTRL+C para parar)")

while True:
    try:
        raw  = urllib.request.urlopen(SERVER_URL, timeout=5).read()
        data = json.loads(raw)

        if data.get("status") in ["ativo", "pensando", "modal"]:
            if data.get("status") == "pensando":
                texto_raw = data.get("fala_robo", "")
            elif data.get("status") == "modal":
                texto_raw = data.get("dados", {}).get("pergunta", "")
            else:
                texto_raw = data.get("dados", {}).get("fala_robo", "")

            texto = limpar_texto(texto_raw)

            if texto and texto != ultimo_texto:
                ultimo_texto = texto
                print("NAO vai falar: " + texto)

                # Escolhe o gesto baseado no texto
                gesto = escolher_gesto(texto)
                anim_path = GESTOS[gesto]
                print("Gesto: " + gesto + " (" + anim_path + ")")

                # Embute a animação no início do texto com tag ^start
                # O NAO dispara a animação E fala ao mesmo tempo
                texto_animado = "^start({}) {}".format(anim_path, texto)

                try:
                    anim.say(texto_animado, config)
                except Exception as e1:
                    print("ALAnimatedSpeech falhou (" + str(e1) + "), usando TTS simples...")
                    try:
                        tts.say(texto)
                    except Exception as e2:
                        print("TTS também falhou: " + str(e2))

    except KeyboardInterrupt:
        print("Encerrando.")
        break
    except Exception as e:
        print("Erro: " + str(e))

    time.sleep(3)