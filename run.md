Terminal 1 (Backend):
cd "C:\work\capstone upd\capstone_handoff"
.venv\Scripts\activate
python -m uvicorn src.api:app --port 8000

Terminal 2 (Frontend):
cd "C:\work\capstone upd\capstone_handoff\frontend"
npm run dev