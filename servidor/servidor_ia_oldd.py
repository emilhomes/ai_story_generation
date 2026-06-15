from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import ollama
from datetime import datetime
import os
import re
import json
from state_manager import manager

app = Flask(__name__)
CORS(app) # Habilita CORS para todas as rotas

MODELO = 'llama3.1'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAIZ_PROJETO = os.path.join(BASE_DIR, "..")
PASTA_HISTORIAS = os.path.join(RAIZ_PROJETO, "historias")
PASTA_GERADAS = os.path.join(RAIZ_PROJETO, "historias_geradas")
PASTA_APRESENTACAO = os.path.join(RAIZ_PROJETO, "apresentacao")

os.makedirs(PASTA_HISTORIAS, exist_ok=True)
os.makedirs(PASTA_GERADAS, exist_ok=True)

# ============================================================
# ROTAS DE ARQUIVOS ESTÁTICOS
# ============================================================

@app.route('/apresentacao/')
def serve_apresentacao_index():
    diretorio = os.path.abspath(os.path.join(BASE_DIR, "..", "apresentacao"))
    return send_from_directory(diretorio, "index.html")

@app.route('/apresentacao/<path:filename>')
def serve_apresentacao_files(filename):
    diretorio = os.path.abspath(os.path.join(BASE_DIR, "..", "apresentacao"))
    return send_from_directory(diretorio, filename)

@app.route('/images/<path:filename>')
def serve_image(filename):
    diretorio = os.path.abspath(os.path.join(BASE_DIR, "..", "historias_geradas"))
    return send_from_directory(diretorio, filename)

# ============================================================
# CONFIGURAÇÃO TOONYOU BETA 6 (Estilo Animação 3D / Pixar)
# ============================================================
ESTILO_TOONYOU = "masterpiece, best quality, 3d style, pixar style, cute cartoon, vivid colors, highly detailed, cinematic lighting"
NEGATIVE_TOONYOU = "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry, (realistic, photorealistic:1.3)"

def montar_prompt_microcena(cena, personagens_globais):
    nomes_presentes = [n.lower() for n in cena.get("personagens", [])]
    desc_txt = ""
    for p in personagens_globais:
        if p.get("nome").lower() in nomes_presentes:
            desc_txt += f"{p['descricao_visual']}, "

    acao = cena.get('acao', 'playing')
    camera = cena.get('camera', 'medium shot')
    emocao = cena.get('emocao', 'happy')
    cenario = cena.get('cenario', 'detailed colorful background')

    # Estrutura SD 1.5: Estilo + Personagem + Ação + Cenário + Tags extras
    prompt = f"{ESTILO_TOONYOU}, {desc_txt} {acao} in {cenario}, {emocao} expression, {camera}, highly detailed scenery"
    return prompt.strip()

def montar_triptico_prompts(microcenas_raw, personagens_globais, student_name, npc_principal):
    """
    Garante 3 quadros com padrão alternado:
      Quadro 1 → ALUNO sozinho
      Quadro 2 → NPC/INVENTOR sozinho
      Quadro 3 → ALUNO + NPC juntos
    Usa a ação/cenário/emoção das microcenas geradas pela IA como base,
    mas força quem aparece em cada quadro.
    """
    # Garante ao menos 3 microcenas (repete a última se necessário)
    while len(microcenas_raw) < 3:
        microcenas_raw.append(microcenas_raw[-1].copy())

    # Monta descrição visual de cada personagem
    desc_por_nome = {}
    for p in personagens_globais:
        desc_por_nome[p["nome"].lower()] = p["descricao_visual"]

    student_desc = desc_por_nome.get(student_name.lower(), "1child, cute student, period-appropriate clothing")
    npc_desc = desc_por_nome.get(npc_principal.lower(), "historical figure, period-appropriate clothing")

    quadros = []

    # Quadro 1 – apenas o aluno
    c1 = microcenas_raw[0]
    q1 = f"{ESTILO_TOONYOU}, {student_desc}, {c1.get('acao','exploring')} in {c1.get('cenario','detailed background')}, {c1.get('emocao','curious')} expression, {c1.get('camera','medium shot')}, highly detailed scenery, solo"
    quadros.append(q1.strip())

    # Quadro 2 – apenas o inventor/NPC
    c2 = microcenas_raw[1]
    q2 = f"{ESTILO_TOONYOU}, {npc_desc}, {c2.get('acao','explaining')} in {c2.get('cenario','detailed background')}, {c2.get('emocao','focused')} expression, {c2.get('camera','medium shot')}, highly detailed scenery, solo"
    quadros.append(q2.strip())

    # Quadro 3 – aluno e inventor juntos
    c3 = microcenas_raw[2]
    q3 = f"{ESTILO_TOONYOU}, {student_desc} and {npc_desc}, {c3.get('acao','collaborating together')} in {c3.get('cenario','detailed background')}, {c3.get('emocao','excited')} expression, {c3.get('camera','wide shot')}, highly detailed scenery, 2people"
    quadros.append(q3.strip())

    return quadros

# ============================================================
# GERAÇÃO DE CONTEÚDO (CONTRATADO PELO STATE MANAGER)
# ============================================================

def gerar_json_seguro(prompt, temperatura=0.4):
    try:
        resposta = ollama.chat(
            model=MODELO, 
            messages=[{'role': 'user', 'content': prompt}], 
            format='json',
            options={'temperature': temperatura, 'num_predict': 1000}
        )
        conteudo = resposta.message.content.strip()
        print(f"\n=== RESPOSTA JSON ===\n{conteudo}\n=====================\n")
        return json.loads(conteudo)
    except Exception as e:
        print(f"❌ Erro no JSON: {e}")
        return {}

def montar_prompt_narrativo(contexto, historico=""):
    prompt = f"""[SYSTEM: BILINGUAL STORYBOARD ENGINE]
Role: Professional Director & Portuguese Narrator.
Style: ToonYou 3D Animation / Pixar style.
Output: Valid JSON only.

### CHARACTER PROTOCOL ###
- The Student ({contexto['student_name']}) is the PROTAGONIST.
- ALWAYS write in the second person ("Você", "Tu") or first person from the perspective of {contexto['student_name']}.
- {contexto['student_name']} is PHYSICALLY PRESENT in the historical scene as an assistant, researcher, or engineer.
- NPCs must interact directly with {contexto['student_name']}.

### LANGUAGE MAP (MANDATORY) ###
- historia (PT-BR) -> Full paragraph for the child (on screen).
- fala_robo (PT-BR) -> VERY SIMPLE version for the NAO robot to speak (max 2 short sentences).
- opcoes (PT-BR) -> 2 choices for the child.
- personagens, microcenas, acao, camera, emocao, cenario (EN-US) -> Technical metadata for images.

### EXAMPLE OF CORRECT BILINGUAL OUTPUT ###
{{
  "historia": "Você está em Londres, 1837. Como assistente de Charles Babbage, você vê o inventor frustrado com erros matemáticos. Ele olha para você e pergunta como resolver isso.",
  "fala_robo": "Estamos em 1837! Você é assistente do Charles Babbage. Ele precisa de ajuda com uma máquina de calcular!",
  "opcoes": ["Construir uma máquina automática", "Contratar mais revisores"],
  "personagens": [
    {{ "nome": "{contexto['student_name']}", "descricao_visual": "1child, cute student, period-appropriate clothing" }},
    {{ "nome": "Charles Babbage", "descricao_visual": "elderly man, 19th century suit, messy hair, holding blueprints" }}
  ],
  "microcenas": [
    {{
      "acao": "Student and Babbage looking at complex blueprints on a wooden table with brass gears around",
      "camera": "medium shot",
      "emocao": "focused",
      "cenario": "19th century workshop, steam coming from pipes, candle light",
      "personagens": ["{contexto['student_name']}", "Charles Babbage"]
    }},
    {{
      "acao": "Close-up of Babbage pointing at a mistake in a table of numbers, looking stressed",
      "camera": "close-up",
      "emocao": "stressed",
      "cenario": "workshop background",
      "personagens": ["Charles Babbage"]
    }},
    {{
      "acao": "Student nodding thoughtfully while touching a brass gear",
      "camera": "medium shot",
      "emocao": "curious",
      "cenario": "workshop with tools and mechanical parts",
      "personagens": ["{contexto['student_name']}"]
    }}
  ]
}}

### CURRENT STORY TASK ###
Student: {contexto['student_name']}
Theme: {contexto['theme']}
Step: {contexto['current_step']}
Historical Context: {contexto['historical_facts']}
Goal: {contexto['goal']}
Emotion: {contexto['emotion']}
Must: {contexto['must_happen']}
Forbidden: {contexto['cannot_happen']}
History: {historico}

[CRITICAL: GENERATE 3 DISTINCT 'microcenas' IN EN-US. BE VERY DETAILED IN 'acao' AND 'cenario'.]
[ACADEMIC RIGOR: ENSURE THE NARRATIVE IS FAITHFUL TO THE 'Historical Context' PROVIDED.]
"""
    if contexto.get("is_final"):
        prompt += "\nIMPORTANT: FINAL STEP. No 'opcoes'. Warm ending."
    
    return prompt

# ============================================================
# PROCESSADOR E ROTAS
# ============================================================
def processar_cena(cena_dados, personagens_globais, sid, num_cena, student_name="", npc_principal=""):
    microcenas = cena_dados.get("microcenas", [])
    
    if not isinstance(microcenas, list) or len(microcenas) == 0:
        microcenas = [{"acao": "character appearing", "camera": "wide shot", "emocao": "neutral", "cenario": "detailed background", "personagens": [p["nome"] for p in personagens_globais]}]
    
    while len(microcenas) < 3:
        microcenas.append(microcenas[-1].copy())

    # CORREÇÃO: usa tríptico alternado (aluno / inventor / juntos)
    if student_name and npc_principal:
        prompts_imagens = montar_triptico_prompts(microcenas[:3], personagens_globais, student_name, npc_principal)
    else:
        prompts_imagens = [montar_prompt_microcena(c, personagens_globais) for c in microcenas[:3]]
    
    # Textos descritivos dos quadros para o log
    textos_quadros = [
        f"[ALUNO] {microcenas[0].get('acao', '')}",
        f"[{npc_principal or 'NPC'}] {microcenas[1].get('acao', '')}",
        f"[JUNTOS] {microcenas[2].get('acao', '')}",
    ]

    # Nomes de arquivo que o story_client.js vai gerar
    imagens_arquivos = [f"sessao_{sid}/cena_{num_cena}_quadro_{i+1}.png" for i in range(len(prompts_imagens))]
    ref_arquivo = f"sessao_{sid}/cena_1_referencia_global.png" if num_cena == 1 else imagens_arquivos[0]

    return {
        "historia": cena_dados.get("historia", ""),
        "fala_robo": cena_dados.get("fala_robo", ""),
        "opcoes": (cena_dados.get("opcoes", []) + ["Continuar", "Explorar"])[:2],
        "prompts_imagens": prompts_imagens,
        "imagens_arquivos": imagens_arquivos,
        "referencia_arquivo": ref_arquivo,
        "microcenas_textos": textos_quadros
    }

# Variável global para o visualizador (PC2) seguir o que o terminal (PC1) está fazendo
SESSAO_ATIVA = {
    "session_id": None,
    "last_scene_data": None
}

@app.route('/iniciar_historia', methods=['POST'])
def iniciar():
    dados = request.json
    nome = dados.get('nome', 'Criança')
    skill = dados.get('skill', 'socializacao')
    tema = dados.get('tema', 'Escola')
    
    sid = manager.create_session(nome, skill, tema)
    ctx = manager.get_current_context(sid)
    
    prompt = montar_prompt_narrativo(ctx)
    cena_raw = gerar_json_seguro(prompt)
    
    personagens = cena_raw.get("personagens", [])
    if not personagens: personagens = [{"nome": "Protagonista", "descricao_visual": "young child, casual outfit"}]
    
    state = manager.load_state(sid)
    state["personagens_globais"] = personagens
    manager.save_state(sid)
    
    proc = processar_cena(cena_raw, personagens, sid, 1, student_name=nome, npc_principal=ctx.get("npc_principal", ""))
    
    # Registra como sessão ativa para o PC2 seguir
    SESSAO_ATIVA["session_id"] = sid
    SESSAO_ATIVA["last_scene_data"] = proc
    
    return jsonify({
        'session_id': sid, 'status': 'sucesso', 'node_id': ctx['current_step'],
        'historia_original': proc['historia'],
        'fala_robo': proc['fala_robo'],
        'prompts_imagens': proc['prompts_imagens'],
        'imagens_arquivos': proc['imagens_arquivos'],
        'referencia_arquivo': proc['referencia_arquivo'],
        'microcenas_textos': proc['microcenas_textos'],
        'negative_prompt': NEGATIVE_TOONYOU,
        'opcoes': proc['opcoes'], 'tem_opcoes': True
    })

@app.route('/escolher', methods=['POST'])
def escolher():
    dados = request.json
    sid = dados.get('session_id')
    escolha = dados.get('escolha_texto', '')
    
    state = manager.advance_state(sid, escolha)
    if not state: return jsonify({'status': 'erro'}), 400
    
    ctx = manager.get_current_context(sid)
    if not ctx: return jsonify({'status': 'sucesso', 'tem_opcoes': False, 'historia_original': "Fim da jornada!"})

    historico_texto = "\n".join([f"Passo: {h['step']}, Escolha: {h['choice']}" for h in state["history"][-2:]])
    
    prompt = montar_prompt_narrativo(ctx, historico_texto)
    cena_raw = gerar_json_seguro(prompt)
    
    personagens = state.get("personagens_globais", [])
    num_cena = state["current_step_idx"] + 1
    proc = processar_cena(cena_raw, personagens, sid, num_cena, student_name=state["student"]["name"], npc_principal=ctx.get("npc_principal", ""))

    # Atualiza dados para o visualizador
    SESSAO_ATIVA["last_scene_data"] = proc

    return jsonify({
        'session_id': sid, 'status': 'sucesso', 'node_id': ctx['current_step'],
        'historia_original': proc['historia'],
        'fala_robo': proc['fala_robo'],
        'prompts_imagens': proc['prompts_imagens'],
        'imagens_arquivos': proc['imagens_arquivos'],
        'referencia_arquivo': proc['imagens_arquivos'][0],
        'microcenas_textos': proc['microcenas_textos'],
        'negative_prompt': NEGATIVE_TOONYOU,
        'opcoes': proc['opcoes'], 'tem_opcoes': not ctx.get('is_final', False)
    })

@app.route('/visualizador/cena_atual')
@app.route('/visualizador/cena_atual/')
def visualizador_cena():
    if not SESSAO_ATIVA["session_id"]:
        return jsonify({"status": "aguardando"})
    return jsonify({
        "status": "ativo",
        "session_id": SESSAO_ATIVA["session_id"],
        "dados": SESSAO_ATIVA["last_scene_data"]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
