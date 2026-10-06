import os

directories = [
    "frontend/css", "frontend/js", "frontend/assets/animals", "frontend/assets/icons",
    "backend/api", "backend/agent", "backend/rag", "backend/services", 
    "backend/database", "backend/data/knowledge", "vector_db", "tests"
]

files = [
    "frontend/css/style.css", "frontend/js/api.js", "frontend/js/camera.js", 
    "frontend/js/voice.js", "frontend/js/map.js",
    "backend/config.py",
    "backend/api/__init__.py", "backend/api/chat.py", "backend/api/vision.py", 
    "backend/api/voice.py", "backend/api/recommendation.py", "backend/api/route.py",
    "backend/agent/__init__.py", "backend/agent/agent.py", "backend/agent/state.py", 
    "backend/agent/decision.py", "backend/agent/tools.py",
    "backend/rag/__init__.py", "backend/rag/retriever.py", "backend/rag/embeddings.py", 
    "backend/rag/vector_store.py", "backend/rag/ingest.py",
    "backend/services/__init__.py", "backend/services/llm.py", "backend/services/vision.py", 
    "backend/services/stt.py", "backend/services/tts.py",
    "backend/database/__init__.py", "backend/database/database.py", "backend/database/models.py",
    "backend/data/zones.json", "backend/data/routes.json",
    "backend/data/knowledge/tiger.txt", "backend/data/knowledge/lion.txt", "backend/data/knowledge/panda.txt",
    "tests/__init__.py", "tests/test_chat.py", "tests/test_rag.py", "tests/test_agent.py", "tests/test_recommendation.py",
    ".env", ".gitignore", "README.md"
]

for d in directories:
    os.makedirs(d, exist_ok=True)

for f in files:
    if not os.path.exists(f):
        with open(f, 'w', encoding='utf-8') as file:
            pass

print("專案升級架構建立完成！")