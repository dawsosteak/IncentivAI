# Get start
pip install openpyxl

# Run the API server via prebuilt image
docker run -p 127.0.0.1:7000:7000 -it karust/openserp serve -a 0.0.0.0 -p 7000

# searching 
cd Tommy
cd Searching
python energy_search.py Texas