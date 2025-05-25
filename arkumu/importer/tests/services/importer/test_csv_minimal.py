import os
import tempfile
import csv

import pytest

@pytest.mark.django_db
def test_csv_reading():
    print("Testing CSV reading...")
    
    # Create a simple test CSV
    test_data = [
        ['id', 'name', 'description'],
        ['1', 'Test Project 1', 'A test project'],
        ['2', 'Test Project 2', 'Another test project']
    ]
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerows(test_data)
        csv_path = f.name
    
    try:
        print(f"1. Created test CSV at: {csv_path}")
        
        print("2. Testing CSV reading with csv.DictReader...")
        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter=';')
            row_count = 0
            for row in reader:
                row_count += 1
                print(f"   Row {row_count}: {row}")
                if row_count > 10:  # Safety break
                    break
        
        print(f"   ✅ Successfully read {row_count} rows")
        
        print("3. Testing the actual import_csv_as_cells function...")
        from arkumu.importer.services.importer.bulk_import import import_csv_as_cells
        
        print("   Calling import_csv_as_cells...")
        stats = import_csv_as_cells(
            csv_file_path=csv_path,
            dataset_name="test_dataset",
            institution="TEST",
            base_uri="http://test.arkumu.org/data",
            delimiter=';',
            has_quoted_fields=False
        )
        
        print(f"   ✅ import_csv_as_cells completed: {stats}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up
        if os.path.exists(csv_path):
            os.unlink(csv_path)

if __name__ == "__main__":
    test_csv_reading() 