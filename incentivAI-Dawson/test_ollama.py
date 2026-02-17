import ollama

# Create a client and set the host (if needed)
client = ollama.Client(base_url="http://127.0.0.1:11434")  # Use your running Ollama server

# Chat with the model
response = client.chat(
    model="llama3.1:8b",
    messages=[{"role": "user", "content": "Hello Ollama"}]
)

print(response["message"]["content"])
