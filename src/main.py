from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routers import diagnose

app = FastAPI(
    title="AutoDiagnoseAI Backend",
    description="Agentic Backend for Vehicle Fault Diagnosis",
    version="1.0.0"
)

# CORS configuration (allow the Vue.js frontend to connect)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For hackathon demo purposes; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(diagnose.router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "AutoDiagnoseAI-Backend"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)
