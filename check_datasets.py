#!/usr/bin/env python3
"""
Check what dataset resources and triples exist in the database
"""
import os
import sys
import django

# Setup Django
sys.path.append('/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()

from arkumu.metadata.models import Resource, Triple
from django.db.models import Q

def check_datasets():
    print("=== CHECKING DATASET RESOURCES AND TRIPLES ===")
    
    # Check if any dataset resources exist
    datasets = Resource.objects.filter(uri__contains='/datasets/')
    print(f'Total dataset resources: {datasets.count()}')

    if datasets.exists():
        print('\nSample dataset resources:')
        for ds in datasets[:5]:
            print(f'  - {ds.uri}')
        
        # Check if any have triples
        sample_dataset = datasets.first()
        print(f'\nChecking triples for: {sample_dataset.uri}')
        
        # As subject
        as_subject = Triple.objects.filter(subject=sample_dataset).count()
        print(f'  As subject: {as_subject} triples')
        
        # As object  
        as_object = Triple.objects.filter(object=sample_dataset).count()
        print(f'  As object: {as_object} triples')
        
        # Check if any entities are linked to datasets
        isPartOf_prop = Resource.objects.filter(uri='http://purl.org/dc/terms/isPartOf').first()
        if isPartOf_prop:
            dataset_entity_links = Triple.objects.filter(predicate=isPartOf_prop, object__uri__contains='/datasets/')
            print(f'\nDataset-entity links found: {dataset_entity_links.count()}')
            if dataset_entity_links.exists():
                print('Sample dataset-entity links:')
                for link in dataset_entity_links[:3]:
                    print(f'  {link.subject.uri} → {link.object.uri}')
        else:
            print('\nNo isPartOf property found')
            
        # Check hasPart relationships (dataset → column)
        hasPart_prop = Resource.objects.filter(uri='http://purl.org/dc/terms/hasPart').first()
        if hasPart_prop:
            dataset_part_links = Triple.objects.filter(predicate=hasPart_prop, subject__uri__contains='/datasets/')
            print(f'\nDataset hasPart links found: {dataset_part_links.count()}')
            if dataset_part_links.exists():
                print('Sample dataset hasPart links:')
                for link in dataset_part_links[:3]:
                    print(f'  {link.subject.uri} → {link.object.uri}')
        else:
            print('\nNo hasPart property found')
            
    else:
        print('No dataset resources found!')
        
    # Check what organization data exists
    fuk_resources = Resource.objects.filter(uri__contains='fuk')
    print(f'\nTotal FUK resources: {fuk_resources.count()}')
    
    if fuk_resources.exists():
        print('Sample FUK resources:')
        for res in fuk_resources[:10]:
            print(f'  - {res.uri}')
    
    print("\n=== INVESTIGATION COMPLETE ===")

if __name__ == "__main__":
    check_datasets()