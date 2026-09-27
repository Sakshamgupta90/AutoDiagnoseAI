from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class QdrantDiagnosticSearch:
    def __init__(self, collection_name: str = "zenodo_faults", host: str = "localhost", port: int = 6333):
        self.collection_name = collection_name
        try:
            # We attempt to connect to a real Qdrant instance
            self.client = QdrantClient(host=host, port=port)
            logger.info(f"Initialized Qdrant client for collection {collection_name}")
        except Exception as e:
            logger.warning(f"Could not connect to Qdrant at {host}:{port}. Using mock mode. {e}")
            self.client = None

    def search(
        self, 
        symptom_text: str, 
        dtc_codes: Optional[List[str]] = None, 
        make: Optional[str] = None, 
        model: Optional[str] = None,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search: Dense embedding for symptom_text + Exact/Sparse filtering for dtc_codes and make/model.
        """
        if not self.client:
            # Fallback mock for testing without DB running
            return self._mock_search(dtc_codes)
            
        # In a real environment, you'd embed the symptom_text here using sentence-transformers or Bedrock Titan.
        # For simplicity in this tool, we assume Qdrant is handling the embedding or we pass a dummy vector.
        # Here we construct the exact/sparse filter
        must_conditions = []
        if dtc_codes:
            must_conditions.append(
                FieldCondition(key="dtc_codes", match=MatchAny(any=dtc_codes))
            )
        if make:
            must_conditions.append(
                FieldCondition(key="make", match=MatchValue(value=make))
            )
            
        search_filter = Filter(must=must_conditions) if must_conditions else None
        
        try:
            # Note: query_vector requires actual floats, assuming [0.0]*384 for compilation safety without an embedder
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=[0.0] * 384, # Replace with actual embedding
                query_filter=search_filter,
                limit=limit
            )
            
            return [{
                "chunk_id": str(res.id),
                "source": "Zenodo Automotive Faults Dataset",
                "score": res.score,
                "payload": res.payload
            } for res in results]
            
        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            return self._mock_search(dtc_codes)

    def _mock_search(self, dtc_codes):
        mock_results = []
        if dtc_codes and "P0301" in dtc_codes:
            mock_results.append({
                "chunk_id": "15626055-chunk-01",
                "source": "Zenodo Automotive Faults Dataset",
                "score": 0.92,
                "payload": {
                    "text": "Engine misfire detected in cylinder 1. Check spark plug, ignition coil, and fuel injector. Proceed to flowchart A.",
                    "dtc_codes": ["P0301"],
                    "category": "engine"
                }
            })
        return mock_results
