
import os
import sys
import django
from pathlib import Path

# Setup Django environment to use settings.py
BASE_DIR = Path(__file__).resolve().parent / "core"
sys.path.append(str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

# Now import LLM
try:
    from claims.services.llm import llm
    print("Testing LLM...")
    res = llm.generate("Hello, are you working?", system_instruction="Respond with 'YES' only.")
    print(f"LLM Response: '{res}'")
except Exception as e:
    import traceback
    traceback.print_exc()
