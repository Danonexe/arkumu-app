#!/usr/bin/env python3
import os
import sys
from typing import Dict, List, Tuple

def extract_model_fields(content: str) -> Dict[str, List[Tuple[str, str]]]:
    """Extract model fields, handling multi-line definitions and avoiding duplicates."""
    models = {}
    current_model = None
    current_fields = {}
    current_field = []
    in_field = False
    current_meta = []  # Store the complete Meta class as lines
    in_meta = False
    
    for line in content.split('\n'):
        if line.strip().startswith('class ') and '(models.Model)' in line:
            if current_model:
                # Process fields before adding to models
                processed_fields = {}
                for field_name, field_def in current_fields.items():
                    processed_fields[field_name] = field_def
                
                models[current_model] = {
                    'fields': list(processed_fields.items()),
                    'meta': current_meta  # Store complete Meta class
                }
            
            current_model = line.split('(')[0].split()[-1]
            current_fields = {}
            current_meta = []
            in_field = False
            in_meta = False
            continue
            
        if line.strip().startswith('class Meta:'):
            in_meta = True
            current_meta.append(line)
            continue
            
        if in_meta:
            if not line.strip():
                in_meta = False
            else:
                current_meta.append(line)
            continue

        if '= models.' in line:
            if current_field:
                field_name = current_field[0]
                field_def = '\n'.join(current_field[1:])
                current_fields[field_name] = field_def
            field_name = line.split('=')[0].strip()
            current_field = [field_name, line.strip()]
            in_field = '(' in line and ')' not in line
            if not in_field:
                current_fields[field_name] = line.strip()
                current_field = []
        elif in_field:
            current_field.append(line.strip())
            if ')' in line:
                in_field = False
                field_name = current_field[0]
                field_def = '\n'.join(current_field[1:])
                current_fields[field_name] = field_def
                current_field = []
    
    # Handle last model
    if current_model and current_fields:
        processed_fields = {}
        for field_name, field_def in current_fields.items():
            processed_fields[field_name] = field_def
        
        models[current_model] = {
            'fields': list(processed_fields.items()),
            'meta': current_meta  # Store complete Meta class
        }
    
    return models

def sort_fields(fields: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Sort fields with id first, then alphabetically."""
    return (
        # id field always first
        [f for f in fields if f[0] == 'id'] +
        # version field second
        [f for f in fields if f[0] == 'version'] +
        # rest of the fields alphabetically
        sorted([f for f in fields if f[0] not in ['id', 'version']], key=lambda x: x[0])
    )

def generate_translations(models: Dict[str, List[Tuple[str, str]]]) -> str:
    """Generate django-modeltranslation registration code."""
    output = [
        "from modeltranslation.translator import register, TranslationOptions",
        "from .models import *\n"
    ]
    
    for model_name, fields in sorted(models.items()):
        # Get translatable fields (those with _de and _en suffixes)
        translatable = set()
        for field_name, _ in fields:
            if field_name.endswith('_de'):
                base = field_name[:-3]
                if any(f[0] == f"{base}_en" for f in fields):
                    translatable.add(base)
        
        if translatable:
            # Sort fields for consistent output
            fields_str = "', '".join(sorted(translatable))
            output.extend([
                f"@register({model_name})",
                f"class {model_name}Translation(TranslationOptions):",
                f"    fields = ('{fields_str}')\n"
            ])
    
    return '\n'.join(output)

def main():
    if len(sys.argv) != 2:
        print("Usage: python sort_and_analyze_models.py <path_to_models.py>")
        sys.exit(1)

    try:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            content = f.read()
        
        models = extract_model_fields(content)
        
        # Generate sorted_models.py
        output = ["from django.db import models\n"]
        for model_name, model_data in sorted(models.items()):
            output.append(f"class {model_name}(models.Model):")
            # model_data now contains 'fields' and 'meta' keys
            for field_name, field_def in sort_fields(model_data['fields']):
                output.append(f"    {field_def}")
            # Add the original Meta class exactly as it was
            output.extend(model_data['meta'])
            output.append("\n")
        
        sorted_models_path = os.path.join(os.path.dirname(__file__), 'models.py')
        with open(sorted_models_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(output))
            
        # Generate translations.py
        translations = generate_translations({name: data['fields'] for name, data in models.items()})
        translations_path = os.path.join(os.path.dirname(__file__), 'translations.py')
        with open(translations_path, 'w', encoding='utf-8') as f:
            f.write(translations)
            
        print(f"Successfully wrote sorted models to {sorted_models_path}")
        print(f"Successfully wrote translations to {translations_path}")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    main()