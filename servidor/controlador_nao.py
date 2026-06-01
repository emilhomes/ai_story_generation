from flask import Flask, request, jsonify
from flask_cors import CORS
import time

# Tente importar o SDK do NAO (apenas no PC conectado ao NAO)
try:
    from naoqi import ALProxy
    NAO_DISPONIVEL = True
except ImportError:
    print("⚠️ SDK NAOQI não encontrado. Rodando em modo SIMULAÇÃO.")
    NAO_DISPONIVEL = False

app = Flask(__name__)
CORS(app)

# CONFIGURAÇÕES DO NAO
NAO_IP = "192.168.x.x"  # Mude para o IP real do seu NAO
NAO_PORT = 9559

def get_nao_proxies():
    if not NAO_DISPONIVEL: return None, None
    try:
        tts = ALProxy("ALTextToSpeech", NAO_IP, NAO_PORT)
        motion = ALProxy("ALMotion", NAO_IP, NAO_PORT)
        return tts, motion
    except Exception as e:
        print("❌ Erro ao conectar ao NAO:", e)
        return None, None

@app.route('/speak', methods=['POST'])
def speak():
    data = request.json
    text = data.get('text', '')
    
    print(f"🤖 NAO deve falar: {text}")
    
    tts, motion = get_nao_proxies()
    
    if tts:
        # Configurações de voz para parecer mais "acolhedor"
        tts.setLanguage("Portuguese")
        tts.setParameter("pitchShift", 1.1) # Voz levemente mais aguda/infantil
        
        # Pequeno movimento de cabeça para dar vida
        if motion:
            motion.setStiffnesses("Head", 1.0)
            motion.post.angleInterpolation(["HeadYaw"], [0.2, -0.2, 0.0], [1.0, 2.0, 3.0], True)
        
        # NAO fala o texto simplificado (Naoguês)
        tts.say(text)
        
        return jsonify({"status": "sucesso", "mode": "real"})
    else:
        # Simulação se o robô não estiver conectado
        time.sleep(len(text) * 0.1) # Simula tempo de fala
        return jsonify({"status": "sucesso", "mode": "simulacao"})

if __name__ == '__main__':
    # Roda na porta 8080 para não conflitar com o Flask da IA (5000)
    app.run(host='0.0.0.0', port=8080, debug=False)
