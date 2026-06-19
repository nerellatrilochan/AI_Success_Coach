import os
import shutil
from typing import List, Dict, Any, Tuple
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document

class RAGService:
    """Production-grade Retrieval Augmented Generation Service using Chroma DB"""
    
    def __init__(self, knowledge_file_path: str = "Knowledge.md", persist_directory: str = "./chroma_db", force_rebuild: bool = False):
        """
        Initialize RAG service with knowledge base
        
        Args:
            knowledge_file_path: Path to the Knowledge.md file
            persist_directory: Directory to persist Chroma DB
            force_rebuild: If True, rebuild vector store from scratch
        """
        self.knowledge_file_path = knowledge_file_path
        self.persist_directory = persist_directory
        self.vector_store = None
        self.embeddings = None
        
        # Force rebuild if requested or if KB file is newer than DB
        if force_rebuild or self._should_rebuild_db():
            print("🔄 Rebuilding vector store from scratch...")
            self._cleanup_vector_store()
            self._create_new_vector_store()
        else:
            # Try to load existing vector store
            self._initialize_vector_store()
    
    def _should_rebuild_db(self) -> bool:
        """Check if Knowledge.md is newer than the vector store"""
        if not os.path.exists(self.persist_directory):
            return True
        
        kb_time = os.path.getmtime(self.knowledge_file_path) if os.path.exists(self.knowledge_file_path) else 0
        db_time = os.path.getmtime(self.persist_directory) if os.path.exists(self.persist_directory) else 0
        
        return kb_time > db_time
    
    def _cleanup_vector_store(self):
        """Remove existing vector store"""
        if os.path.exists(self.persist_directory):
            print(f"🗑️  Cleaning up old vector store...")
            shutil.rmtree(self.persist_directory)
    
    def _load_knowledge_base(self) -> str:
        """Load the Knowledge.md file"""
        if not os.path.exists(self.knowledge_file_path):
            raise FileNotFoundError(f"Knowledge base file not found: {self.knowledge_file_path}")
        
        with open(self.knowledge_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"📖 Loaded knowledge base ({len(content)} characters, {content.count(chr(10))} lines)")
        return content
    
    def _split_into_sections(self, content: str) -> List[Tuple[str, str]]:
        """
        First, split content by major sections (# heading level)
        Returns list of (section_title, section_content) tuples
        """
        sections = []
        current_section = "Introduction"
        current_content = []
        
        lines = content.split('\n')
        
        for line in lines:
            if line.startswith('# ') and current_content:
                # Save previous section
                section_title = current_section
                section_content = '\n'.join(current_content).strip()
                if section_content:
                    sections.append((section_title, section_content))
                
                # Start new section
                current_section = line.replace('# ', '').strip()
                current_content = [line]
            else:
                current_content.append(line)
        
        # Save final section
        if current_content:
            sections.append((current_section, '\n'.join(current_content).strip()))
        
        print(f"📑 Identified {len(sections)} major sections")
        return sections
    
    def _split_section_into_chunks(self, section_title: str, section_content: str, chunk_size: int = 2000, chunk_overlap: int = 400) -> List[Document]:
        """
        Split a section into chunks while preserving subsections
        """
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=[
                "\n## ",      # Subsections first
                "\n### ",     # Sub-subsections
                "\n\n",       # Paragraphs
                "\n",         # Lines
                " ",          # Words
                ""            # Characters
            ]
        )
        
        chunks = splitter.split_text(section_content)
        
        # Create documents with rich metadata
        documents = []
        for i, chunk in enumerate(chunks):
            # Include section title for better context
            content_with_context = f"[Section: {section_title}]\n\n{chunk}"
            
            documents.append(
                Document(
                    page_content=content_with_context,
                    metadata={
                        "source": "Knowledge.md",
                        "section": section_title,
                        "chunk_index": i,
                        "chunk_size": len(chunk)
                    }
                )
            )
        
        return documents
    
    def _split_into_chunks(self, content: str) -> List[Document]:
        """
        Intelligent chunking: First split by sections, then by subsections
        This preserves semantic meaning better than flat chunking
        """
        # Step 1: Split by major sections
        sections = self._split_into_sections(content)
        
        # Step 2: Split each section into chunks
        all_documents = []
        for section_title, section_content in sections:
            docs = self._split_section_into_chunks(section_title, section_content)
            all_documents.extend(docs)
        
        print(f"✂️  Split into {len(all_documents)} semantic chunks")
        return all_documents
    
    def _initialize_vector_store(self):
        """Initialize or load Chroma vector store"""
        try:
            if os.path.exists(self.persist_directory) and os.listdir(self.persist_directory):
                print("📚 Loading existing Chroma vector store...")
                self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
                self.vector_store = Chroma(
                    persist_directory=self.persist_directory,
                    embedding_function=self.embeddings
                )
                print("✓ Vector store loaded successfully")
                return
        except Exception as e:
            print(f"⚠️  Error loading vector store: {e}")
        
        # Create new if load failed
        self._create_new_vector_store()
    
    def _create_new_vector_store(self):
        """Create a new Chroma vector store from Knowledge.md"""
        print("🔨 Creating new Chroma vector store...")
        
        # Load knowledge base
        content = self._load_knowledge_base()
        
        # Split into chunks intelligently
        documents = self._split_into_chunks(content)
        
        # Initialize embeddings
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        print("🧮 Generating embeddings...")
        
        # Create Chroma vector store
        self.vector_store = Chroma.from_documents(
            documents=documents,
            embedding=self.embeddings,
            persist_directory=self.persist_directory
        )
        
        print(f"✓ Vector store created with {len(documents)} chunks")
    
    def retrieve_relevant_context(self, query: str, k: int = 7) -> List[Dict[str, Any]]:
        """
        Retrieve relevant documents from the vector store
        
        IMPORTANT: No hard threshold filtering - return ALL results and let LLM decide
        
        Args:
            query: User's question
            k: Number of top results to retrieve
            
        Returns:
            List of relevant documents with content
        """
        if not self.vector_store:
            raise ValueError("Vector store not initialized")
        
        print(f"🔍 Searching vector store for: '{query}'")
        
        # Perform similarity search with scores
        results = self.vector_store.similarity_search_with_score(query, k=k)
        
        if not results:
            print("⚠️  No results found in vector store")
            return []
        
        formatted_results = []
        for i, (doc, score) in enumerate(results):
            # Convert distance to similarity (lower distance = higher similarity)
            similarity = 1 - score  # OpenAI embeddings return distances
            
            formatted_results.append({
                "rank": i + 1,
                "content": doc.page_content,
                "relevance_score": round(similarity, 4),
                "source": doc.metadata.get("source", "Knowledge.md"),
                "section": doc.metadata.get("section", "Unknown"),
                "chunk_index": doc.metadata.get("chunk_index", -1)
            })
            
            print(f"  [{i+1}] Relevance: {similarity:.4f}, Section: {doc.metadata.get('section')}")
        
        return formatted_results
    
    def get_answer_from_knowledge_base(self, llm, query: str, k: int = 7) -> str:
        """
        Generate answer using LLM with retrieved context from knowledge base
        
        Args:
            llm: LangChain LLM instance
            query: User's question
            k: Number of context chunks to retrieve
            
        Returns:
            Generated answer based on knowledge base
        """
        from langchain_core.messages import SystemMessage, HumanMessage
        
        print(f"\n📝 Processing query: '{query}'")
        
        # Retrieve relevant context
        retrieved_docs = self.retrieve_relevant_context(query, k=k)
        
        if not retrieved_docs:
            print("❌ No relevant documents found")
            return """I couldn't find relevant information in the knowledge base. 

Please try asking about:
- **Learning Portal Access** (how to log in, accessing learning.ccbp.in)
- **Home Page** (dashboard, events, performance metrics)
- **My Journey** (growth cycles, milestones, progress tracking)
- **Course Exams** (exam schedules, how they work, retakes)
- **Course Certificates** (eligibility, issuance, access)
- **Search** (how to search for content)
- **Bookmarks** (saving questions, accessing bookmarks)
- **Bonus Courses** (additional learning opportunities)
- **LastMinute Pro** (placement preparation)

Could you rephrase your question or ask about one of these topics?"""
        
        # Format context for LLM with all metadata
        context_parts = []
        for result in retrieved_docs:
            context_parts.append(
                f"""
<Context_{result['rank']}>
Section: {result['section']}
Relevance Score: {result['relevance_score']}
---
{result['content']}
</Context_{result['rank']}>
"""
            )
        
        context = "\n".join(context_parts)
        
        # Create comprehensive system prompt
        system_prompt = """You are Success Coach AI, an expert assistant helping students with CCBP 4.0 Academy.

YOUR ROLE:
- Answer questions about CCBP Academy Learning Portal, courses, features, and platform functionality
- Provide accurate, complete information from the knowledge base
- Give step-by-step instructions when relevant
- Be helpful, friendly, and student-focused

INSTRUCTIONS:
1. Use the provided context to answer the question
2. Be thorough and specific - include all relevant details
3. If the context answers the question completely, provide a complete answer
4. Organize information with clear sections and bullet points
5. Always cite the relevant section from the knowledge base
6. Use friendly, encouraging language
7. If information seems incomplete from one context chunk, look across multiple chunks

IMPORTANT: Do NOT say "I couldn't find relevant information" - The context provided contains relevant information. Use it to answer the question thoroughly.

KNOWLEDGE BASE CONTEXT:
{context}

---

Now answer the student's question comprehensively using the context provided. Be detailed and complete."""
        
        user_message = query
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ]
        
        print("🤖 Generating response from LLM...")
        
        # Generate answer
        response = llm.invoke(messages).content
        
        print("✓ Response generated successfully")
        return response


def initialize_rag_service(knowledge_file_path: str = "Knowledge.md", force_rebuild: bool = False) -> RAGService:
    """
    Initialize and return RAG service
    
    Args:
        knowledge_file_path: Path to Knowledge.md file
        force_rebuild: If True, rebuild vector store from scratch
        
    Returns:
        Initialized RAGService instance
    """
    return RAGService(knowledge_file_path=knowledge_file_path, force_rebuild=force_rebuild)