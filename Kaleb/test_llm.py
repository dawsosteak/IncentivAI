from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate

model = OllamaLLM(model="llama3.2", temperature=0.1)
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a strict analyst. Output exactly YES or NO."),
    ("human", "Say something else")
])
chain = prompt | model
print(chain.invoke({}))
