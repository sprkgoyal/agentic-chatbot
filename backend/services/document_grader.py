from typing import List, Tuple, Callable, Optional
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from services.llm_factory import get_llm

class DocumentRelevance(BaseModel):
    """Structured response for document relevance grading."""
    is_relevant: bool = Field(
        description="True if the document contains information that is relevant to the user query, False otherwise."
    )
    explanation: str = Field(
        description="A brief 1-sentence explanation of why the document is relevant or not."
    )

def get_grader_chain():
    """Initializes the LLM-based document grading chain using structured outputs."""
    # We use a fast, cost-effective model (mini or flash) for grading
    llm = get_llm(temperature=0.0)
    structured_llm = llm.with_structured_output(DocumentRelevance)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an expert auditor grading retrieved documents for relevance to a user query.\n"
            "Analyze the document content and determine if it contains information directly related or useful "
            "to answer the user's query.\n"
            "Be generous but accurate: if the document contains keywords, code, architectural information, "
            "or context that might help answer the query, mark it as relevant.\n"
            "Return a structured evaluation."
        )),
        ("human", (
            "User Query: {query}\n\n"
            "Retrieved Document:\n"
            "--- START DOCUMENT ---\n"
            "Source: {source}\n"
            "Content:\n{content}\n"
            "--- END DOCUMENT ---"
        ))
    ])
    
    return prompt | structured_llm

def grade_and_filter_documents(
    query: str, 
    documents: List[Document], 
    status_callback: Optional[Callable[[str], None]] = None
) -> List[Document]:
    """
    Grades all retrieved documents against the user query.
    Filters out documents scored as irrelevant.
    """
    if not documents:
        return []
        
    if status_callback:
        status_callback(f"Grading {len(documents)} retrieved documents for relevance...")
        
    grader = get_grader_chain()
    filtered_docs = []
    pruned_count = 0
    
    for i, doc in enumerate(documents):
        source_name = doc.metadata.get("file_path") or doc.metadata.get("title") or doc.metadata.get("source") or "Unknown"
        
        try:
            # Invoke the grading chain
            grading: DocumentRelevance = grader.invoke({
                "query": query,
                "source": source_name,
                "content": doc.page_content
            })
            
            if grading.is_relevant:
                filtered_docs.append(doc)
                if status_callback:
                    status_callback(f"--> [KEEP] Document '{source_name}' is relevant: {grading.explanation}")
            else:
                pruned_count += 1
                if status_callback:
                    status_callback(f"--> [PRUNE] Document '{source_name}' filtered out: {grading.explanation}")
        except Exception as e:
            # In case of API failure, default to keeping the document to avoid data loss
            print(f"Error grading document: {e}")
            filtered_docs.append(doc)
            if status_callback:
                status_callback(f"--> [KEEP] Error grading '{source_name}', kept as fallback.")
                
    if status_callback and pruned_count > 0:
        status_callback(f"🧹 Pruned {pruned_count} irrelevant documents from the context.")
        
    return filtered_docs
