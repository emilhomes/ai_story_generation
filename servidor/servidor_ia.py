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
NEGATIVE_TOONYOU = "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry, (realistic, photorealistic:1.3), (3 people, 4 people, crowd:1.4), merged faces, merged bodies, fused characters, extra person, duplicate character"

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
    3 quadros com separação clara de personagens:
      Quadro 1 → ALUNO sozinho  (solo, 1person)
      Quadro 2 → NPC/INVENTOR sozinho  (solo, 1person)
      Quadro 3 → ALUNO + NPC lado a lado  (2people, side by side, wide shot)

    Usa ação/cenário/emoção das microcenas geradas pela IA como base.
    """
    while len(microcenas_raw) < 3:
        microcenas_raw.append(microcenas_raw[-1].copy())

    desc_por_nome = {}
    for p in personagens_globais:
        desc_por_nome[p["nome"].lower()] = p["descricao_visual"]

    student_desc = desc_por_nome.get(student_name.lower(), "1child, cute student, period-appropriate clothing")
    npc_desc     = desc_por_nome.get(npc_principal.lower(), "1man, historical figure, period-appropriate clothing")

    quadros = []

    # ---------- Quadro 1: ALUNO sozinho ----------
    c1 = microcenas_raw[0]
    q1 = (
        f"{ESTILO_TOONYOU}, "
        f"solo, 1person, 1child, {student_desc}, "
        f"{c1.get('acao','looking around curiously')} in {c1.get('cenario','detailed colorful background')}, "
        f"{c1.get('emocao','curious')} expression, {c1.get('camera','medium shot')}, "
        f"highly detailed scenery"
    )
    quadros.append(q1)

    # ---------- Quadro 2: NPC sozinho ----------
    c2 = microcenas_raw[1]
    q2 = (
        f"{ESTILO_TOONYOU}, "
        f"solo, 1person, 1man, {npc_desc}, "
        f"{c2.get('acao','explaining something important')} in {c2.get('cenario','detailed colorful background')}, "
        f"{c2.get('emocao','focused')} expression, {c2.get('camera','medium shot')}, "
        f"highly detailed scenery"
    )
    quadros.append(q2)

    # ---------- Quadro 3: JUNTOS (composição lateral) ----------
    c3 = microcenas_raw[2]
    # Técnica SD 1.5: descrever posição explícita ("on the left", "on the right")
    # e usar "2people" + "wide shot" para o modelo não inventar terceiros
    q3 = (
        f"{ESTILO_TOONYOU}, "
        f"2people, wide shot, "
        f"on the left: 1child {student_desc}, "
        f"on the right: 1man {npc_desc}, "
        f"both {c3.get('acao','looking at each other')} in {c3.get('cenario','detailed colorful background')}, "
        f"{c3.get('emocao','engaged')} expressions, "
        f"highly detailed scenery"
    )
    quadros.append(q3)

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

def montar_prompt_narrativo(contexto, historico="", student_visual_fixo=""):
    # Se já temos o visual fixo do aluno, incluímos no prompt para o LLM não inventar outro
    student_visual_instruction = (
        f"FIXED VISUAL (use EXACTLY as is, do not change): {student_visual_fixo}"
        if student_visual_fixo
        else (
            "Generate a DETAILED physical description including: "
            "hair color and style, eye color, skin tone, clothing color and style, "
            "any distinctive feature. Example: '1child, short curly brown hair, green eyes, "
            "light skin, wearing a white linen shirt and dark brown trousers, small leather satchel'"
        )
    )

    prompt = f"""[SYSTEM: BILINGUAL STORYBOARD ENGINE]
Role: Professional Director & Portuguese Narrator.
Style: ToonYou 3D Animation / Pixar style.
Output: Valid JSON only.

### CHARACTER PROTOCOL ###
- The Student ({contexto['student_name']}) is the PROTAGONIST.
- ALWAYS write in the second person ("Você", "Tu") or first person from the perspective of {contexto['student_name']}.
- {contexto['student_name']} is PHYSICALLY PRESENT in the historical scene as an assistant, researcher, or engineer.
- NPCs must interact directly with {contexto['student_name']}.

### STUDENT VISUAL ###
{student_visual_instruction}

### LANGUAGE MAP (MANDATORY) ###
- historia (PT-BR) -> Full paragraph for the child (on screen).
- fala_robo (PT-BR) -> VERY SIMPLE version for the NAO robot to speak (max 2 short sentences).
- opcoes (PT-BR) -> 2 choices for the child.
- personagens, microcenas, acao, camera, emocao, cenario (EN-US) -> Technical metadata for images.

### MICROCENAS RULES (CRITICAL FOR IMAGE GENERATION) ###
- microcena 1: STUDENT ONLY — describe the student's solo action. personagens: ["{contexto['student_name']}"]
- microcena 2: NPC ONLY — describe the NPC/inventor solo action. personagens: [NPC name]
- microcena 3: BOTH TOGETHER — describe a shared action. personagens: ["{contexto['student_name']}", NPC name]
- NEVER put both characters in microcena 1 or 2.

### EXAMPLE OF CORRECT BILINGUAL OUTPUT ###
{{
  "historia": "Você está em Londres, 1837. Como assistente de Charles Babbage, você vê o inventor frustrado com erros matemáticos. Ele olha para você e pergunta como resolver isso.",
  "fala_robo": "Estamos em 1837! Você é assistente do Charles Babbage. Ele precisa de ajuda com uma máquina de calcular!",
  "opcoes": ["Construir uma máquina automática", "Contratar mais revisores"],
  "personagens": [
    {{ "nome": "{contexto['student_name']}", "descricao_visual": "1child, short curly brown hair, green eyes, light skin, white linen shirt, dark brown trousers, small leather satchel, period 19th century clothing" }},
    {{ "nome": "Charles Babbage", "descricao_visual": "1man, elderly, short grey hair, pale skin, dark Victorian suit with white cravat, holding rolled blueprints, wire-frame glasses" }}
  ],
  "microcenas": [
    {{
      "acao": "Student carefully examining brass gears on a wooden workbench, eyes wide with curiosity",
      "camera": "medium shot",
      "emocao": "curious",
      "cenario": "19th century workshop, steam coming from pipes, candle light, gears and tools everywhere",
      "personagens": ["{contexto['student_name']}"]
    }},
    {{
      "acao": "Babbage pointing at a mistake in a table of numbers, looking frustrated and stressed",
      "camera": "medium shot",
      "emocao": "stressed",
      "cenario": "19th century workshop, stacks of paper, ink wells, large window with foggy London outside",
      "personagens": ["Charles Babbage"]
    }},
    {{
      "acao": "Student and Babbage standing side by side at a large table covered in blueprints, both looking at the same drawing",
      "camera": "wide shot",
      "emocao": "focused",
      "cenario": "19th century workshop, warm candlelight, brass instruments on shelves",
      "personagens": ["{contexto['student_name']}", "Charles Babbage"]
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

[CRITICAL: FOLLOW MICROCENAS RULES ABOVE. microcena 1 = student solo. microcena 2 = NPC solo. microcena 3 = both.]
[ACADEMIC RIGOR: ENSURE THE NARRATIVE IS FAITHFUL TO THE 'Historical Context' PROVIDED.]
"""
    if contexto.get("is_final"):
        prompt += "\nIMPORTANT: FINAL STEP. No 'opcoes'. Warm ending."
    
    return prompt

# ============================================================
# CHARACTER SHEET — mantém a aparência do aluno consistente
# ============================================================
def fixar_visual_aluno(personagens, student_name, state):
    """
    Na primeira cena: salva o descricao_visual do aluno no state como 'student_visual_fixed'.
    Nas cenas seguintes: substitui qualquer nova descrição gerada pelo LLM pelo valor salvo,
    garantindo que a aparência seja idêntica em todos os quadros.
    Retorna a lista de personagens com o aluno corrigido.
    """
    student_visual_fixo = state.get("student_visual_fixed")

    for p in personagens:
        if p.get("nome", "").lower() == student_name.lower():
            if not student_visual_fixo:
                # Primeira cena: guardar o que o LLM gerou
                state["student_visual_fixed"] = p["descricao_visual"]
                student_visual_fixo = p["descricao_visual"]
            else:
                # Cenas seguintes: blindar a descrição
                p["descricao_visual"] = student_visual_fixo
            break

    return personagens


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
    
    # Primeira cena: ainda não há visual fixo, o LLM vai criar
    prompt = montar_prompt_narrativo(ctx, student_visual_fixo="")
    cena_raw = gerar_json_seguro(prompt)
    
    personagens = cena_raw.get("personagens", [])
    if not personagens:
        personagens = [{"nome": nome, "descricao_visual": "1child, short brown hair, brown eyes, light skin, period-appropriate clothing"}]
    
    state = manager.load_state(sid)
    # Fixa o visual do aluno e salva no state
    personagens = fixar_visual_aluno(personagens, nome, state)
    state["personagens_globais"] = personagens
    manager.save_state(sid)
    
    proc = processar_cena(cena_raw, personagens, sid, 1, student_name=nome, npc_principal=ctx.get("npc_principal", ""))
    
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
    
    # Passa o visual fixo do aluno para o LLM não inventar outro
    student_visual_fixo = state.get("student_visual_fixed", "")
    prompt = montar_prompt_narrativo(ctx, historico_texto, student_visual_fixo=student_visual_fixo)
    cena_raw = gerar_json_seguro(prompt)

    # Garante que o visual do aluno nos personagens gerados seja o fixo
    personagens = state.get("personagens_globais", [])
    novos_personagens = cena_raw.get("personagens", [])
    if novos_personagens:
        # Atualiza descrições de NPCs novos, mas blinda o aluno
        for np in novos_personagens:
            if np.get("nome", "").lower() != state["student"]["name"].lower():
                # NPC novo ou atualizado: adiciona/atualiza na lista global
                nomes_existentes = [p["nome"].lower() for p in personagens]
                if np["nome"].lower() not in nomes_existentes:
                    personagens.append(np)
        fixar_visual_aluno(personagens, state["student"]["name"], state)
        state["personagens_globais"] = personagens
        manager.save_state(sid)

    num_cena = state["current_step_idx"] + 1
    proc = processar_cena(cena_raw, personagens, sid, num_cena, student_name=state["student"]["name"], npc_principal=ctx.get("npc_principal", ""))

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
