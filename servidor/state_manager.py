import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ESTADOS_DIR = os.path.join(BASE_DIR, "..", "historias", "estados")
os.makedirs(ESTADOS_DIR, exist_ok=True)

# ============================================================
# BLUEPRINTS NARRATIVOS (A ESTRUTURA REAL)
# ============================================================
BLUEPRINTS = {
    "historia_computacao": {
        "steps": [
            {
                "id": "maquina_analitica",
                "npc_principal": "Charles Babbage",
                "goal": "Introduce the student as Babbage's assistant in 1837 London. Present the problem of mathematical errors in maritime tables.",
                "historical_facts": "Charles Babbage noticed that human 'computers' made many errors in mathematical tables used for navigation. The Analytical Engine included a 'Store' (memory), a 'Mill' (processor), and used punch cards inspired by Jacquard looms. It was the first design for a general-purpose computer.",
                "emotion": "frustration",
                "cannot_happen": "modern technology, robots",
                "must_happen": "Babbage asks: 'Como podemos reduzir esses erros?', choices about building a machine or hiring people"
            },
            {
                "id": "ada_lovelace",
                "npc_principal": "Ada Lovelace",
                "goal": "The student is a researcher analyzing the Analytical Engine project with Ada Lovelace. She proposes the idea of sequences of instructions.",
                "historical_facts": "Ada Lovelace translated Luigi Menabrea's memoir on the machine and added her own 'Notes'. In 'Note G', she wrote the first algorithm intended for a machine: a method to calculate Bernoulli numbers. She realized the machine could manipulate symbols, not just numbers, potentially creating music or art.",
                "emotion": "inspiration",
                "cannot_happen": "purely numerical focus without question",
                "must_happen": "Ada asks: 'O que acha?', choices about step-by-step instructions or numerical limits"
            },
            {
                "id": "turing",
                "npc_principal": "Alan Turing",
                "goal": "Cambridge, 1936. Student is with Alan Turing. He's tackling computability.",
                "historical_facts": "In his paper 'On Computable Numbers', Turing introduced the concept of a Universal Machine. It used an infinite tape with symbols and a read/write head. He proved that some problems (like the Halting Problem) are undecidable, defining the limits of what computers can do.",
                "emotion": "contemplation",
                "cannot_happen": "computers already existing",
                "must_happen": "Turing asks: 'Como saber se um problema pode ser resolvido por uma máquina?', choices about symbols on a tape or traditional proof"
            },
            {
                "id": "arpanet",
                "npc_principal": "Vint Cerf",
                "goal": "Student is an engineer in the ARPANET project. Discussion about network failure and university connection.",
                "historical_facts": "ARPANET was the first network to implement TCP/IP and packet switching. The first message was sent between UCLA and SRI in 1969. The message was supposed to be 'LOGIN', but the system crashed after 'LO'. It aimed to connect researchers across the US reliably.",
                "emotion": "urgency",
                "cannot_happen": "internet already existing",
                "must_happen": "Scientists ask for opinion on connection failure, choices about packets or exclusive connections"
            }
        ]
    },
    "socializacao": {
        "steps": [
            {
                "id": "safe_intro",
                "goal": "Introduce the main character and the environment in a warm, safe way.",
                "emotion": "calm",
                "cannot_happen": "conflict, danger, rejection",
                "must_happen": "friendly atmosphere"
            },
            {
                "id": "observe_character",
                "goal": "The protagonist observes other characters performing an interesting activity.",
                "emotion": "curiosity",
                "cannot_happen": "pressure to act, bullying",
                "must_happen": "visual validation of others"
            },
            {
                "id": "small_interaction",
                "goal": "A small and safe interaction (e.g., a wave, a smile, a simple question).",
                "emotion": "gentleness",
                "cannot_happen": "error, punishment, shame",
                "must_happen": "positive response from the other character"
            },
            {
                "id": "positive_feedback",
                "goal": "The other character validates the interaction and invites the protagonist for something simple.",
                "emotion": "mild joy",
                "cannot_happen": "exclusion",
                "must_happen": "invitation or acceptance"
            },
            {
                "id": "shared_activity",
                "goal": "Perform a short and pleasant joint activity.",
                "emotion": "cooperation",
                "cannot_happen": "aggressive competition",
                "must_happen": "shared success"
            },
            {
                "id": "warm_ending",
                "goal": "Comfortable closure with the promise of meeting again.",
                "emotion": "satisfaction",
                "cannot_happen": "sadness of goodbye",
                "must_happen": "feeling of 'I did it'"
            }
        ]
    }
}

class StateManager:
    def __init__(self):
        self.sessions = {}

    def create_session(self, student_name, focus_skill, theme):
        session_id = str(datetime.now().timestamp()).replace(".", "")
        blueprint = BLUEPRINTS.get(focus_skill, BLUEPRINTS["socializacao"])
        
        state = {
            "session_id": session_id,
            "student": {
                "name": student_name,
                "focus_skill": focus_skill,
                "theme": theme
            },
            "current_step_idx": 0,
            "blueprint": blueprint,
            "history": [],
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "last_update": datetime.now().isoformat()
            }
        }
        
        self.sessions[session_id] = state
        self.save_state(session_id)
        return session_id

    def advance_state(self, session_id, choice_text):
        state = self.load_state(session_id)
        if not state:
            return None
            
        state["history"].append({"choice": choice_text, "step": state["blueprint"]["steps"][state["current_step_idx"]]["id"]})
        state["current_step_idx"] += 1
        state["metadata"]["last_update"] = datetime.now().isoformat()
        
        self.sessions[session_id] = state
        self.save_state(session_id)
        return state

    def get_current_context(self, session_id):
        state = self.load_state(session_id)
        if not state:
            return None
            
        idx = state["current_step_idx"]
        if idx >= len(state["blueprint"]["steps"]):
            return None
            
        step = state["blueprint"]["steps"][idx]
        return {
            "student_name": state["student"]["name"],
            "theme": state["student"]["theme"],
            "current_step": step["id"],
            "npc_principal": step.get("npc_principal", ""),
            "goal": step["goal"],
            "historical_facts": step.get("historical_facts", ""),
            "emotion": step["emotion"],
            "cannot_happen": step["cannot_happen"],
            "must_happen": step["must_happen"],
            "is_final": idx == len(state["blueprint"]["steps"]) - 1
        }

    def save_state(self, session_id):
        state = self.sessions.get(session_id)
        if not state:
            return
            
        file_path = os.path.join(ESTADOS_DIR, f"sessao_{session_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def load_state(self, session_id):
        # Primeiro tenta na memória
        if session_id in self.sessions:
            return self.sessions[session_id]
            
        # Depois no disco
        file_path = os.path.join(ESTADOS_DIR, f"sessao_{session_id}.json")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                state = json.load(f)
                self.sessions[session_id] = state
                return state
        return None

# Instância global
manager = StateManager()
