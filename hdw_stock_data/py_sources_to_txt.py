# Read multiple Python files and combine them into a single text file
with open("hdw_stock_data.txt", "w", encoding="utf-8") as output_file:
    for filename in ["__init__.py",
                     "exceptions.py",
                     "loader.py",
                     "normalizer.py",
                     "result.py",
                     "version.py",
                     "yahoo_client.py",
                     "..\\test_assets.py",
                     "..\\settings.json", 
                     ]:  # List your Python files here
        with open(filename, "r", encoding="utf-8") as input_file:
            content = input_file.read()
            output_file.write(f"--- Start of {filename} ---\n")
            output_file.write(content)
            output_file.write(f"\n--- End of {filename} ---\n\n")   
