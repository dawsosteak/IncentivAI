# Clone and build V 0.5.4
git clone https://github.com/karust/openserp.git
cd openserp
go build -o openserp .

# Run the server
./openserp serve

# searching 
python states.py "Texas"