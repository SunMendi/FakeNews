
import os
import sys
import django
from pathlib import Path

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent / "core"
sys.path.append(str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from claims.services.search import hybrid_passage_search
from claims.services.verdict import build_verdict

query = "ইরাকের কুর্দিস্তানে মার্কিন সামরিক ঘাঁটিতে ড্রোন হামলা"
print(f"Searching for: {query}")
passages = hybrid_passage_search(query)
print(f"Found {len(passages)} passages.")

print("Calling Semantic Judge...")
result = build_verdict(query, passages)
print(f"Verdict: {result.verdict}")
print(f"Confidence: {result.confidence_percent}")
print(f"Explanation: {result.explanation}")
