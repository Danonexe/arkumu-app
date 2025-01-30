#!/usr/bin/env python3
import re
import sys
from collections import defaultdict

def find_language_suffixed_fields(models_content):
    # Regular expression to match class definitions
    class_pattern = r'class (\w+)\(models\.Model\):\s+(.*?)(?=\s*class|$)'
    
    # Regular expression to match field definitions with _en or _de suffixes
    field_pattern = r'(\w+_(?:en|de))\s*=\s*models\.'
    
    # Dictionary to store results
    results = {}
    
    # Find all class definitions and their content
    classes = re.finditer(class_pattern, models_content, re.DOTALL)
    
    for class_match in classes:
        class_name = class_match.group(1)
        class_content = class_match.group(2)
        
        # Find all fields with language suffixes
        fields = re.findall(field_pattern, class_content)
        
        if fields:
            # Group fields by their base name (without suffix)
            grouped_fields = {}
            for field in fields:
                base_name = field[:-3]  # Remove _en or _de
                if base_name not in grouped_fields:
                    grouped_fields[base_name] = []
                grouped_fields[base_name].append(field)
            
            # Only include fields that have both _en and _de versions
            multilingual_fields = {
                base: fields 
                for base, fields in grouped_fields.items() 
                if len(fields) > 1
            }
            
            if multilingual_fields:
                results[class_name] = multilingual_fields
    
    return results

if len(sys.argv) != 2:
    print("Usage: python analyze_translatable_fields.py <path_to_models.py>")
    sys.exit(1)

models_path = sys.argv[1]

# Read the models.py file from the provided path
try:
    with open(models_path, 'r', encoding='utf-8') as file:
        models_content = file.read()
except FileNotFoundError:
    print(f"Error: Could not find file at {models_path}")
    sys.exit(1)
except Exception as e:
    print(f"Error reading file: {e}")
    sys.exit(1)

# Get the results
results = find_language_suffixed_fields(models_content)

# Create a dictionary to count field occurrences
field_occurrences = defaultdict(list)

# Count occurrences of each base field name
for class_name, fields in results.items():
    for base_name in fields.keys():
        field_occurrences[base_name].append(class_name)

# Write the results to a text file
with open('fields_to_translate.txt', 'w', encoding='utf-8') as output_file:
    output_file.write("Models with multilingual fields:\n")
    output_file.write("================================\n")
    
    # Write the detailed results
    for class_name, fields in results.items():
        output_file.write(f"\n{class_name}:\n")
        for base_name, field_versions in fields.items():
            output_file.write(f"  {base_name}: {', '.join(field_versions)}\n")
    
    # Write the summary of field occurrences, sorted by number of occurrences
    output_file.write("\n\nField Occurrences Summary:\n")
    output_file.write("========================\n")
    
    # Sort by number of occurrences (descending) and then alphabetically for ties
    sorted_fields = sorted(
        field_occurrences.items(),
        key=lambda x: (-len(x[1]), x[0])
    )
    
    for field_name, classes in sorted_fields:
        output_file.write(f"\n{field_name}:\n")
        output_file.write(f"  Appears in {len(classes)} models:\n")
        for class_name in sorted(classes):
            output_file.write(f"    - {class_name}\n")

print("Results have been written to 'fields_to_translate.txt'")