"""
diagnostico_nao.py
Rode este script no PC do NAO (172.16.60.67) com:
    python diagnostico_nao.py

Ele testa cada estratégia de conexão e diz qual funciona.
"""
import sys, os, subprocess, json, socket

NAO_IP   = "172.16.61.45"
NAO_PORT = 9559

print("=" * 55)
print("  DIAGNÓSTICO DE CONEXÃO COM O NAO")
print("=" * 55)
print(f"  Python: {sys.version}")
print(f"  NAO alvo: {NAO_IP}:{NAO_PORT}\n")

# ----------------------------------------------------------
# TESTE 0: conectividade básica de rede
# ----------------------------------------------------------
print("[ TESTE 0 ] Ping TCP ao NAO...")
try:
    s = socket.create_connection((NAO_IP, NAO_PORT), timeout=3)
    s.close()
    print("  ✅ Porta 9559 acessível!\n")
    porta_ok = True
except Exception as e:
    print(f"  ❌ Não consegue alcançar {NAO_IP}:9559 — {e}")
    print("  → Verifique se o NAO está ligado e na mesma rede.\n")
    porta_ok = False

# ----------------------------------------------------------
# TESTE 1: qi (Python 3 nativo)
# ----------------------------------------------------------
print("[ TESTE 1 ] Importando 'qi' (Python 3)...")
try:
    import qi
    print("  ✅ 'qi' importado com sucesso!")
    if porta_ok:
        print("  → Tentando conectar ao NAO...")
        try:
            app = qi.Application(["--qi-url", f"tcp://{NAO_IP}:{NAO_PORT}"])
            app.start()
            tts = app.session.service("ALTextToSpeech")
            tts.say("Olá! Conexão com qi funcionando!")
            print("  ✅ NAO falou via qi!\n")
        except Exception as e:
            print(f"  ❌ qi conectou mas falhou ao falar: {e}\n")
    else:
        print("  ⚠️  Pulando teste de fala (sem rede).\n")
    QI_OK = True
except ImportError:
    print("  ❌ 'qi' não instalado neste Python.")
    print("  → No Windows: copie qi.pyd das DLLs do SDK NAOqi para a pasta do projeto.")
    print("  → No Linux/Mac: pip install qi\n")
    QI_OK = False

# ----------------------------------------------------------
# TESTE 2: naoqi (Python 2)
# ----------------------------------------------------------
print("[ TESTE 2 ] Procurando Python 2 com naoqi...")
candidatos = [
    r"C:\Program Files (x86)\Softbank Robotics\Choregraphe Suite 2\bin\python.exe",
    r"C:\Program Files\Softbank Robotics\Choregraphe Suite 2\bin\python.exe",
    r"C:\Program Files (x86)\Aldebaran\Choregraphe Suite 2\bin\python.exe",
    r"C:\NAOqi\bin\python.exe",
    r"C:\Python27\python.exe",
    "python2",
    "python2.7",
]
py2 = None
for p in candidatos:
    try:
        if os.path.isfile(p) or not os.path.sep in p:
            r = subprocess.run([p, "--version"], capture_output=True, timeout=3)
            if r.returncode == 0:
                py2 = p
                print(f"  ✅ Python 2 encontrado: {p}")
                break
    except Exception:
        pass

if not py2:
    print("  ❌ Python 2 não encontrado.")
    print("  → Instale Python 2.7 ou o Choregraphe da SoftBank.")
    print("  → O SDK NAOqi para Windows inclui Python 2.7 embutido.\n")
else:
    if porta_ok:
        script = f"""
import sys
sys.path.insert(0, r'C:\\Program Files (x86)\\Softbank Robotics\\Choregraphe Suite 2\\lib')
try:
    from naoqi import ALProxy
    tts = ALProxy("ALTextToSpeech", "{NAO_IP}", {NAO_PORT})
    tts.say("Teste Python dois funcionando!")
    print("ok")
except Exception as e:
    print("err:" + str(e))
"""
        r = subprocess.run([py2, "-c", script], capture_output=True, timeout=20)
        saida = r.stdout.decode("utf-8", errors="replace").strip()
        if "ok" in saida:
            print("  ✅ NAO falou via Python 2!\n")
        else:
            print(f"  ❌ Python 2 falhou: {saida or r.stderr.decode()}\n")
    else:
        print("  ⚠️  Pulando teste de fala (sem rede).\n")

# ----------------------------------------------------------
# RESUMO
# ----------------------------------------------------------
print("=" * 55)
print("  RESUMO")
print("=" * 55)
if not porta_ok:
    print("  ❌ NAO não está acessível na rede.")
    print("     Verifique IP, cabo/WiFi e se o robô está ligado.")
elif QI_OK:
    print("  ✅ Use a estratégia qi (já funciona!)")
    print("     O controlador_nao.py vai usá-la automaticamente.")
elif py2:
    print("  ✅ Use a estratégia Python 2 subprocess.")
    print("     O controlador_nao.py vai usá-la automaticamente.")
    print(f"     Confirme que PYTHON2_PATH='{py2}' está no controlador.")
else:
    print("  ⚠️  Nenhuma estratégia funcionou.")
    print("     Opções:")
    print("     1) Instale o Choregraphe SDK (inclui Python 2.7 + naoqi)")
    print("        https://community.aldebaran.com/en/resources/software")
    print("     2) Copie qi.pyd do SDK para a pasta do projeto (Python 3)")
print("=" * 55)
