# app.py
import os

# Prevent Hugging Face from making network calls to HF Hub on every query
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from pathlib import Path
import streamlit as st
import pixeltable as pxt
from pixeltable import exceptions as pxt_exceptions
from pixelagent.openai import Agent
from tools import financial_tool

from openai import OpenAI

# 1. Initialize minimal interface
st.set_page_config(page_title="Equity Research Agent", layout="centered")
st.title("Financial Research Assistant")

# 2. Setup Authentication
os.environ["OPENAI_BASE_URL"] = "https://api.groq.com/openai/v1"
os.environ["OPENAI_API_KEY"] = st.secrets["GROQ_API_KEY"]

# 3. Dedicated Robust Agent
# Executes direct Pixeltable vector similarity search over document chunks
# and synthesizes results via Groq without fragile database write-locks or recursive tool call failures.
class FinancialResearchAgent:
    def __init__(self, model: str = "openai/gpt-oss-120b"):
        self.model = model
        self.client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=st.secrets["GROQ_API_KEY"]
        )
        self.system_prompt = (
            "You are a professional equity research analyst. Be concise, "
            "factual, and strictly use the retrieved vector DB chunks to "
            "answer. Maintain a clean, corporate tone. If the context does "
            "not contain sufficient information to answer the question, state that clearly."
        )

    def tool_call(self, query: str, top_k: int = 3) -> str:
        chunks_t = pxt.get_table("context_engineering.document_chunks")
        sim = chunks_t.text.similarity(string=query)
        matches = (
            chunks_t.order_by(sim, asc=False)
            .select(chunks_t.text, similarity=sim)
            .limit(top_k)
            .collect()
        )

        if not matches:
            return "No relevant documents found in the database. Please make sure a financial report has been uploaded."

        context_chunks = [
            f"[Chunk {i+1} - Similarity: {r['similarity']:.3f}]:\n{r['text']}"
            for i, r in enumerate(matches)
        ]
        context_str = "\n\n---\n\n".join(context_chunks)

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"User Question: {query}\n\nRetrieved Financial Document Chunks:\n{context_str}"}
        ]

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=3000,
            reasoning_effort="medium"
        )
        return resp.choices[0].message.content

@st.cache_resource
def get_agent():
    return FinancialResearchAgent()

# 4. Sidebar for Drag-and-Drop File Upload
with st.sidebar:
    st.header("Document Ingestion")
    uploaded_file = st.file_uploader("Drop financial reports (PDF) here", type=["pdf"])

    if uploaded_file is not None:
        file_path = f"./{uploaded_file.name}"
        file_uri = Path(file_path).resolve().as_uri()
        documents_t = pxt.get_table("context_engineering.documents")

        # Check the DATABASE using canonical URI and local path representation
        # to avoid false negatives and continuous re-ingestion across reruns
        already_ingested = (
            documents_t.where(
                (documents_t.pdf == file_uri) | (documents_t.pdf == file_path)
            ).count()
            > 0
        )

        if not already_ingested:
            with st.spinner("Processing document for the first time..."):
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                try:
                    documents_t.insert([{"pdf": file_uri}])
                    st.session_state.ingested_file = uploaded_file.name
                    st.success(f"Successfully ingested: {uploaded_file.name}")
                except Exception as e:
                    st.warning("File already exists in memory or encountered an error.")
        else:
            st.success(f"Ready for analysis: {uploaded_file.name}")

# 5. Main Chat Interface
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display persisted conversation history across reruns
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

query = st.chat_input("Ask a question (e.g., 'What are the assumptions for the DCF or SOTP valuation?')")

if query:
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.write(query)

    with st.spinner("Analyzing semantic memory..."):
        agent = get_agent()
        try:
            response = agent.tool_call(query)
        except Exception as e:
            response = f"Sorry, something went wrong generating a response: {e}"

    st.session_state.messages.append({"role": "assistant", "content": response})
    with st.chat_message("assistant"):
        st.write(response)

        