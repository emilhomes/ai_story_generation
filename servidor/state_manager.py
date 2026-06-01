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
            "goal": step["goal"],
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
