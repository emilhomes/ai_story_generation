from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import subprocess
import sys
import os
import json

app = Flask(__name__)
CORS(app)

# ============================================================
# CONFIGURAÇÕES
# ============================================================
NAO_IP   = "172.16.61.45"
NAO_PORT = 9559

# Caminho do Python 2.7 que vem junto com o SDK NAOqi no Windows.
# Ajuste se o seu SDK estiver em outro lugar.
PYTHON2_CANDIDATOS = [
    r"C:\Program Files (x86)\Softbank Robotics\Choregraphe Suite 2\bin\python.exe",
    r"C:\Program Files\Softbank Robotics\Choregraphe Suite 2\bin\python.exe",
    r"C:\Program Files (x86)\Aldebaran\Choregraphe Suite 2\bin\python.exe",
    r"C:\NAOqi\bin\python.exe",
    r"C:\Python27\python.exe",
    "python2",
    "python2.7",
]

# ============================================================
# ESTRATÉGIA 1 — qi (libqi, Python 3 nativo, Linux/Mac)
# ============================================================
try:
    import qi
    QI_DISPONIVEL = True
    print("✅ qi SDK encontrado (Python 3 nativo).")
except ImportError:
    QI_DISPONIVEL = False
    print("ℹ️  qi SDK não encontrado.")

# ============================================================
# ESTRATÉGIA 2 — subprocesso Python 2 com naoqi
# ============================================================
def _encontrar_python2():
    for p in PYTHON2_CANDIDATOS:
        if os.path.isfile(p):
            return p
        try:
            r = subprocess.run([p, "--version"], capture_output=True, timeout=3)
            if r.returncode == 0:
                return p
        except Exception:
            pass
    return None

PYTHON2_PATH = _encontrar_python2()
if PYTHON2_PATH:
    print(f"✅ Python 2 encontrado em: {PYTHON2_PATH}")
else:
    print("ℹ️  Python 2 com naoqi não encontrado.")

# Script inline que o subprocesso Python 2 executa
_PY2_SCRIPT = r"""
import sys, json
args = json.loads(sys.argv[1])
try:
    from naoqi import ALProxy
    tts    = ALProxy("ALTextToSpeech", args["ip"], args["port"])
    motion = ALProxy("ALMotion",        args["ip"], args["port"])
    tts.setLanguage("Portuguese")
    tts.setParameter("pitchShift", 1.1)
    motion.setStiffnesses("Head", 1.0)
    motion.post.angleInterpolation(
        ["HeadYaw"], [0.2, -0.2, 0.0], [1.0, 2.0, 3.0], True
    )
    tts.say(args["text"].encode("utf-8"))
    print("ok")
except Exception as e:
    print("err:" + str(e))
"""

def _falar_via_py2(text):
    """Executa o script naoqi num subprocesso Python 2."""
    if not PYTHON2_PATH:
        return False, "Python 2 não encontrado"
    payload = json.dumps({"ip": NAO_IP, "port": NAO_PORT, "text": text})
    try:
        r = subprocess.run(
            [PYTHON2_PATH, "-c", _PY2_SCRIPT, payload],
            capture_output=True, timeout=30
        )
        saida = r.stdout.decode("utf-8", errors="replace").strip()
        if saida.startswith("err:"):
            return False, saida
        return True, "py2"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, str(e)

# ============================================================
# ESTRATÉGIA 3 — qi via TCP direto (Python 3, sem lib extra)
# Usa o protocolo MessagePack/qi mínimo para chamar ALTextToSpeech
# ============================================================
def _falar_via_qi_nativo(text):
    """
    Usa o módulo qi se disponível (instalado com 'pip install qi' no Linux,
    ou copiando as DLLs do SDK NAOqi para a pasta do projeto no Windows).
    """
    if not QI_DISPONIVEL:
        return False, "qi não instalado"
    try:
        app_qi = qi.Application(["--qi-url", f"tcp://{NAO_IP}:{NAO_PORT}"])
        app_qi.start()
        session = app_qi.session
        tts    = session.service("ALTextToSpeech")
        motion = session.service("ALMotion")
        tts.setLanguage("Portuguese")
        tts.setParameter("pitchShift", 1.1)
        motion.setStiffnesses("Head", 1.0)
        motion.post.angleInterpolation(
            ["HeadYaw"], [0.2, -0.2, 0.0], [1.0, 2.0, 3.0], True
        )
        tts.say(text)
        return True, "qi"
    except Exception as e:
        return False, str(e)

# ============================================================
# ROTA /speak
# ============================================================
@app.route('/speak', methods=['POST'])
def speak():
    data = request.json or {}
    text = data.get('text', '').strip()
    if not text:
        return jsonify({"status": "erro", "motivo": "texto vazio"}), 400

    print(f"\n🤖 NAO deve falar: {text}")

    # Tenta qi Python 3 primeiro (mais rápido, sem subprocesso)
    ok, modo = _falar_via_qi_nativo(text)
    if ok:
        print(f"   ✅ Falado via {modo}")
        return jsonify({"status": "sucesso", "mode": modo})

    print(f"   ⚠️  qi falhou ({modo}), tentando Python 2...")

    # Fallback: subprocesso Python 2 com naoqi
    ok, modo = _falar_via_py2(text)
    if ok:
        print(f"   ✅ Falado via subprocesso Python 2")
        return jsonify({"status": "sucesso", "mode": "py2_subprocess"})

    print(f"   ⚠️  Python 2 falhou ({modo}), entrando em simulação.")

    # Último recurso: simulação
    time.sleep(max(1, len(text) * 0.05))
    return jsonify({"status": "sucesso", "mode": "simulacao", "aviso": modo})

# ============================================================
# ROTA /status  — útil para debug de rede entre os dois PCs
# ============================================================
@app.route('/status', methods=['GET'])
def status():
    return jsonify({
        "qi_disponivel":     QI_DISPONIVEL,
        "python2_path":      PYTHON2_PATH or "não encontrado",
        "nao_ip":            NAO_IP,
        "nao_port":          NAO_PORT,
    })

if __name__ == '__main__':
    print(f"\n🌐 Controlador NAO rodando em 0.0.0.0:8080")
    print(f"   NAO alvo: {NAO_IP}:{NAO_PORT}")
    print(f"   Para testar do PC de IA: curl http://172.16.60.67:8080/status\n")
    app.run(host='0.0.0.0', port=8080, debug=False)
