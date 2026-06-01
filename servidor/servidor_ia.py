import ollama
from flask import Flask, request, jsonify
from datetime import datetime
import os
import re
import json
from state_manager import manager

app = Flask(__name__)

MODELO = 'llama3.1'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PASTA_HISTORIAS = os.path.join(BASE_DIR, "..", "historias")
os.makedirs(PASTA_HISTORIAS, exist_ok=True)

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

### LANGUAGE MAP (MANDATORY) ###
- historia (PT-BR) -> Full paragraph for the child.
- opcoes (PT-BR) -> 2 choices for the child.
- personagens, microcenas, acao, camera, emocao, cenario (EN-US) -> Technical metadata for images.

### EXAMPLE OF CORRECT BILINGUAL OUTPUT ###
{{
  "historia": "João chegou na escola nova com um frio na barriga. Ele viu seus colegas brincando no pátio e respirou fundo, sentindo o perfume das flores no jardim. Com um sorriso tímido, ele começou a caminhar em direção ao grupo, pronto para sua primeira grande aventura.",
  "opcoes": ["Acenar para o grupo", "Observar a brincadeira"],
  "personagens": [{{ "nome": "João", "descricao_visual": "1boy, cute child, blonde hair, blue shirt, school uniform" }}],
  "microcenas": [
    {{
      "acao": "Boy walking slowly through school gates, looking around with a shy smile",
      "camera": "wide shot",
      "emocao": "curious",
      "cenario": "sunny school playground, colorful slides, trees",
      "personagens": ["João"]
    }},
    {{
      "acao": "Boy standing near a flower bed, taking a deep breath of the flowers",
      "camera": "medium shot",
      "emocao": "calm",
      "cenario": "vibrant school garden, blooming roses, sunlight filtering through leaves",
      "personagens": ["João"]
    }},
    {{
      "acao": "Close-up of the boy's face showing a bright, hopeful expression",
      "camera": "close-up",
      "emocao": "happy",
      "cenario": "blurred background of school children playing",
      "personagens": ["João"]
    }}
  ]
}}

### CURRENT STORY TASK ###
Student: {contexto['student_name']}
Theme: {contexto['theme']}
Step: {contexto['current_step']}
Goal: {contexto['goal']}
Emotion: {contexto['emotion']}
Must: {contexto['must_happen']}
Forbidden: {contexto['cannot_happen']}
History: {historico}

[CRITICAL: GENERATE 3 DISTINCT 'microcenas' IN EN-US. BE VERY DETAILED IN 'acao' AND 'cenario'.]
"""
    if contexto.get("is_final"):
        prompt += "\nIMPORTANT: FINAL STEP. No 'opcoes'. Warm ending."
    
    return prompt

# ============================================================
# PROCESSADOR E ROTAS
# ============================================================
def processar_cena(cena_dados, personagens_globais):
    microcenas = cena_dados.get("microcenas", [])
    
    # Se não houver microcenas, cria um fallback básico
    if not isinstance(microcenas, list) or len(microcenas) == 0:
        microcenas = [{"acao": "character appearing", "camera": "wide shot", "emocao": "neutral", "cenario": "detailed background", "personagens": [p["nome"] for p in personagens_globais]}]
    
    # Se tiver menos de 3, repete a última até completar 3 (em vez de descartar tudo)
    while len(microcenas) < 3:
        microcenas.append(microcenas[-1].copy())
    
    prompts_imagens = [montar_prompt_microcena(c, personagens_globais) for c in microcenas[:3]]
    
    return {
        "historia": cena_dados.get("historia", ""),
        "opcoes": (cena_dados.get("opcoes", []) + ["Continuar", "Explorar"])[:2],
        "prompts_imagens": prompts_imagens,
        "microcenas_textos": [c.get("acao", "") for c in microcenas[:3]]
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
    
    # Atualiza personagens na sessão (opcional, mas bom para consistência)
    state = manager.load_state(sid)
    state["personagens_globais"] = personagens
    manager.save_state(sid)
    
    proc = processar_cena(cena_raw, personagens)
    
    return jsonify({
        'session_id': sid, 'status': 'sucesso', 'node_id': ctx['current_step'],
        'historia_original': proc['historia'],
        'prompts_imagens': proc['prompts_imagens'],
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
    if not ctx: # Final da blueprint
        return jsonify({'status': 'sucesso', 'tem_opcoes': False, 'historia_original': "Fim da jornada de hoje!"})

    # Pega histórico recente para o prompt
    historico_texto = "\n".join([f"Passo: {h['step']}, Escolha: {h['choice']}" for h in state["history"][-2:]])
    
    prompt = montar_prompt_narrativo(ctx, historico_texto)
    cena_raw = gerar_json_seguro(prompt)
    
    personagens = state.get("personagens_globais", [])
    proc = processar_cena(cena_raw, personagens)

    return jsonify({
        'session_id': sid, 'status': 'sucesso', 'node_id': ctx['current_step'],
        'historia_original': proc['historia'],
        'prompts_imagens': proc['prompts_imagens'],
        'microcenas_textos': proc['microcenas_textos'],
        'negative_prompt': NEGATIVE_TOONYOU,
        'opcoes': proc['opcoes'], 'tem_opcoes': not ctx.get('is_final', False)
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
