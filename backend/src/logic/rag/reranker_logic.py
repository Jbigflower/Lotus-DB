from typing import List, Union
import pyarrow as pa
from lancedb.rerankers import Reranker
from lancedb.rerankers import CrossEncoderReranker as LanceCrossEncoderReranker
from config.setting import settings

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

class BaseReRanker(Reranker):
    """Base class for reranking strategies."""
    
    def rerank_hybrid(
        self,
        query: str,
        vector_results: pa.Table,
        fts_results: pa.Table,
    ) -> Union[pa.Table, None]:
        """
        Rerank hybrid search results.
        Default implementation returns None, meaning no reranking logic provided here.
        """
        return None


class CrossEncoderReRanker(LanceCrossEncoderReranker, BaseReRanker):
    """
    Wrapper for LanceDB's built-in CrossEncoderReranker.
    """
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2", **kwargs):
        super().__init__(model_name=model_name, **kwargs)


class OllamaEncoderReranker(BaseReRanker):
    """
    Reranker using LLM for list-wise ranking.
    """
    def __init__(self, model_name: str = None, text_col: str = "document"):
        super().__init__()
        self.text_col = text_col
        self.model_name = model_name or settings.llm.deepseek_model
        
        if OpenAI is None:
            raise ImportError("openai is not installed, but it is required for OllamaEncoderReranker.")
            
        self.client = OpenAI(
            api_key=settings.llm.deepseek_api_key,
            base_url=settings.llm.deepseek_base_url,
        )
        self.prompt_template = """You are a relevance ranker. Rank the following passages based on their relevance to the user query.
        User Query: {query}
        
        Passages:
        {passages}
        
        Output ONLY the IDs of the passages in order of relevance, separated by commas.
        Example: 1, 3, 2
        """

    def rerank_hybrid(
        self,
        query: str,
        vector_results: pa.Table,
        fts_results: pa.Table,
    ) -> pa.Table:
        # Merge results
        combined = vector_results
        if fts_results:
             # This is a simplification. Real merging logic depends on how lancedb does it.
             # Usually Reranker.merge(vector_results, fts_results) is used.
             # But here we assume we get a merged table or we merge them.
             # For simplicity, let's assume we just use vector_results for now or implement a simple merge.
             # In lancedb, rerank_hybrid is responsible for merging.
             combined = self.merge(vector_results, fts_results)

        if len(combined) == 0:
            return combined

        # Extract text and IDs
        df = combined.to_pandas()
        passages = []
        for idx, row in df.iterrows():
            content = row.get(self.text_col, "")
            # We use index as ID for ranking
            passages.append(f"ID: {idx}\nContent: {content[:200]}...") # Truncate for context

        passages_str = "\n\n".join(passages)
        
        # Call LLM (Synchronously? Reranker usually is sync in lancedb interface?)
        # Wait, lancedb Reranker methods are not async. 
        # But ChatOpenAI.invoke is sync (blocking).
        
        try:
            prompt = self.prompt_template.format(query=query, passages=passages_str)
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )
            response_text = response.choices[0].message.content or ""
            ranked_ids = [int(i.strip()) for i in response_text.split(",") if i.strip().isdigit()]
            
            # Reorder df
            # Filter valid IDs
            valid_ids = [i for i in ranked_ids if i in df.index]
            # Append missing IDs (if any) at the end
            remaining = [i for i in df.index if i not in valid_ids]
            final_order = valid_ids + remaining
            
            df_ranked = df.loc[final_order].reset_index(drop=True)
            return pa.Table.from_pandas(df_ranked)
            
        except Exception as e:
            # Fallback: return original
            print(f"Reranking failed: {e}")
            return combined
