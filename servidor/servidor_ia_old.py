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
    3 quadros com apenas UM personagem cada para melhor geração de imagem:
      Quadro 1 → ALUNO sozinho (solo, 1person)
      Quadro 2 → NPC sozinho (solo, 1person)
      Quadro 3 → ALUNO sozinho (outra ação/ângulo) (solo, 1person)

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

    # ---------- Quadro 3: ALUNO sozinho (Close-up ou ação de reação) ----------
    c3 = microcenas_raw[2]
    q3 = (
        f"{ESTILO_TOONYOU}, "
        f"solo, 1person, 1child, {student_desc}, "
        f"{c3.get('acao','interacting or reacting')} in {c3.get('cenario','detailed colorful background')}, "
        f"{c3.get('emocao','focused')} expression, {c3.get('camera','close-up')}, "
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
            options={'temperature': temperatura, 'num_predict': 1000},
            keep_alive=0
        )
        conteudo = resposta.message.content.strip()
        print(f"\n=== RESPOSTA JSON ===\n{conteudo}\n=====================\n")
        return json.loads(conteudo)
    except Exception as e:
        print(f"❌ Erro no JSON: {e}")
        return {}

def montar_prompt_narrativo(contexto, historico="", student_visual_fixo=""):
    # Se já temos o visual fixo do aluno, incluímos no prompt para o LLM não inventar outro
    genero_instrucao = f"GENDER: {contexto.get('student_genero', 'Masculino')}"
    
    student_visual_instruction = (
        f"FIXED VISUAL (use EXACTLY as is, do not change): {student_visual_fixo}"
        if student_visual_fixo
        else (
            f"Generate a DETAILED physical description for a {contexto.get('student_genero', 'Masculino')} child (8-12 years old) including: "
            "hair color and style, eye color, skin tone, clothing color and style, "
            "any distinctive feature. Example: '1boy, 10 years old, short messy brown hair, green eyes, "
            "light skin, wearing a white linen shirt and dark brown trousers'. "
            "CRITICAL: The student is a CHILD. They must look COMPLETELY DIFFERENT from the adult NPC."
        )
    )

    npc_visual_instruction = ""
    if contexto.get("npc_visual"):
        npc_visual_instruction = f"- THE NPC ({contexto.get('npc_principal')}) VISUAL MUST BE EXACTLY: '{contexto.get('npc_visual')}' (Do not invent or change this)."

    scenery_guideline = contexto.get("scenery_guideline", "")
    scenery_instruction = f"### SCENERY ATMOSPHERE (MANDATORY GUIDELINE) ###\n{scenery_guideline}" if scenery_guideline else ""

    prompt = f"""[SYSTEM: BILINGUAL STORYBOARD ENGINE]
Role: Professional Director & Portuguese Narrator.
Style: ToonYou 3D Animation / Pixar style.
Output: Valid JSON only.

### CHARACTER PROTOCOL ###
- The Student ({contexto['student_name']}) is the PROTAGONIST and is a CHILD (8-12 years old).
- {genero_instrucao}
- ALWAYS write in the second person ("Você", "Tu") or first person from the perspective of {contexto['student_name']}.
- {contexto['student_name']} is PHYSICALLY PRESENT in the historical scene as an assistant, researcher, or engineer.
- NPCs must interact directly with {contexto['student_name']}.
- CRITICAL: {contexto['student_name']} (CHILD) and {contexto.get('npc_principal')} (ADULT) must have distinct visual descriptions. NEVER reuse the NPC description for the student.
{npc_visual_instruction}

### STUDENT VISUAL ###
{student_visual_instruction}

{scenery_instruction}

### JSON SCHEMA & LANGUAGE RULES (STRICT ENFORCEMENT) ###
You MUST return ONLY a JSON object matching this exact schema. Pay close attention to the requested LANGUAGE for each field.
{{
  "historia": "string (MUST BE PT-BR) - Rich, immersive paragraph (4-6 sentences) describing the atmosphere and current event. Do NOT summarize.",
  "fala_robo": "string (MUST BE PT-BR) - Short friendly comment by the robot.",
  "opcoes": ["string (PT-BR)", "string (PT-BR)"],
  "personagens": [
    {{
      "nome": "string",
      "descricao_visual": "string (MUST BE EN-US) - The exact physical description."
    }}
  ],
  "microcenas": [
    {{
      "acao": "string (MUST BE EN-US) - What the character is doing right now (e.g., 'Student looking at the gears').",
      "camera": "string (MUST BE EN-US) - Camera angle. VARY THIS! Choose from: 'close-up', 'medium shot', 'full body shot', 'low angle', 'high angle', 'dutch angle', 'extreme close-up'.",
      "emocao": "string (MUST BE EN-US) - Character's emotion (e.g., 'amazed', 'focused').",
      "cenario": "string (MUST BE STRICTLY EN-US) - Highly detailed scenery description. NO PORTUGUESE ALLOWED. Example: 'large 1930s laboratory, dark wooden desks, glowing lamps, brass mechanical calculators, dusty bookshelves'",
      "personagens": ["string (Character Name)"]
    }}
  ]
}}

[CRITICAL FATAL ERROR WARNING]: The image generator ONLY understands English. If you write 'acao', 'camera', 'emocao', or 'cenario' in Portuguese, the system will CRASH. DO NOT TRANSLATE THEM TO PORTUGUESE.

### MICROCENAS RULES (CRITICAL FOR IMAGE GENERATION) ###
- Each microcena must have ONLY ONE character (solo).
- microcena 1: STUDENT ONLY ({contexto['student_name']}). personagens: ["{contexto['student_name']}"]
- microcena 2: NPC ONLY ({contexto.get('npc_principal', 'NPC')}). Use strong visual descriptors for the NPC. personagens: ["{contexto.get('npc_principal', 'NPC')}"]
- microcena 3: STUDENT ONLY ({contexto['student_name']}). DIFFERENT action or close-up. personagens: ["{contexto['student_name']}"]
- NEVER swap characters between scenes.
- CRITICAL CAMERA RULE: You MUST use a DIFFERENT camera angle for each microcena to create a dynamic storyboard. Do not repeat angles.
- CRITICAL SCENERY RULE: NEVER use references like "same as before". Each microcena is generated independently. Write a fully standalone, highly detailed scenery description (IN ENGLISH) for EACH micro-scene.

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

[CRITICAL: TECHNICAL METADATA MUST BE IN ENGLISH.]
[CRITICAL: EACH MICROCENA MUST HAVE ONLY ONE CHARACTER (SOLO).]
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
        f"[ALUNO-2] {microcenas[2].get('acao', '')}",
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
    genero = dados.get('genero', 'Masculino')
    
    sid = manager.create_session(nome, skill, tema)
    ctx = manager.get_current_context(sid)
    
    # Salva o gênero no estado para persistência
    state = manager.load_state(sid)
    state["student"]["genero"] = genero
    
    # Primeira cena: ainda não há visual fixo, o LLM vai criar
    prompt = montar_prompt_narrativo(ctx, student_visual_fixo="")
    cena_raw = gerar_json_seguro(prompt)
    
    personagens = cena_raw.get("personagens", [])
    if not personagens:
        desc_padrao = "1boy" if genero == "Masculino" else "1girl"
        personagens = [{"nome": nome, "descricao_visual": f"{desc_padrao}, short hair, brown eyes, light skin, period-appropriate clothing"}]
    
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

    historico_texto = ""
    if state["history"]:
        historico_texto = "### PREVIOUS CHAPTERS (FOR CONTINUITY) ###\n"
        for h in state["history"]:
            # Tenta recuperar o texto da história gerada para cada passo para o LLM saber o que já foi dito
            historico_texto += f"- Step {h['step']}: User chose '{h['choice']}'\n"
    
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
